import json
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.db import Store, now


@pytest.fixture
def settings(tmp_path):
    fixture = Path(__file__).with_name("fake_cli.py")
    fixture.chmod(0o755)
    return Settings(data_dir=tmp_path, api_key="test-secret-do-not-leak", base_url="https://invalid.example/v1",
                    cli=str(fixture), timeout=5)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def session(client):
    response = client.post("/api/sessions", json={"title":"测试工作"})
    assert response.status_code == 201
    return response.json()["id"]


def send(client, sid, text="case:normal", request_id="unique-request-1"):
    return client.post(f"/api/sessions/{sid}/messages", json={"content":text,"request_id":request_id})


def finished(client, rid, timeout=10):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        run=client.get(f"/api/runs/{rid}").json()
        if run["status"] not in {"queued","running"}:
            return run
        time.sleep(0.05)
    pytest.fail("run did not finish")


def test_run_resume_and_immutable_artifacts(client):
    sid=session(client)
    run=send(client,sid).json()
    assert finished(client,run["id"])["status"]=="succeeded"
    first=client.get(f"/api/sessions/{sid}").json()
    assert first["session"]["cli_session_id"]=="test-thread"
    assert len(first["messages"])==2
    first_zip=client.get(f'/api/artifacts/{first["artifacts"][0]["id"]}/download').content
    run2=send(client,sid,request_id="unique-request-2").json()
    assert finished(client,run2["id"])["status"]=="succeeded"
    content=client.get(f"/api/sessions/{sid}/file",params={"path":"outputs/result.txt"}).json()
    assert content["content"]=="continued"
    with zipfile.ZipFile(BytesIO(first_zip)) as archive:
        assert archive.read("outputs/result.txt")==b"first run"
        assert not any("agent-home" in name for name in archive.namelist())
    assert len(client.get(f"/api/sessions/{sid}").json()["artifacts"])==2


def test_idempotency_and_session_lock(client):
    sid=session(client)
    first=send(client,sid,"case:slow")
    repeated=send(client,sid,"case:slow")
    conflict=send(client,sid,"case:slow","different-request")
    assert first.json()["id"]==repeated.json()["id"]
    assert conflict.status_code==409
    assert finished(client,first.json()["id"])["status"]=="succeeded"
    assert len(client.get(f"/api/sessions/{sid}").json()["messages"])==2


def test_concurrent_sessions_keep_files_separate(client):
    a,b=session(client),session(client)
    r1=send(client,a,"case:slow").json()
    r2=send(client,b,"case:slow").json()
    assert finished(client,r1["id"])["status"]=="succeeded"
    assert finished(client,r2["id"])["status"]=="succeeded"
    settings=client.app.state.settings
    assert (settings.data_dir/"sessions"/a/"workspace/outputs/result.txt").exists()
    assert (settings.data_dir/"sessions"/b/"workspace/outputs/result.txt").exists()


def test_failure_and_missing_completion_are_not_success(client):
    sid=session(client)
    for case in ["case:failure","case:missing-completion"]:
        run=send(client,sid,case,"request-"+case).json()
        result=finished(client,run["id"])
        assert result["status"]=="failed"
        assert result["error"]


def test_cancellation_stops_process(client):
    sid=session(client)
    run=send(client,sid,"case:hang").json()
    deadline=time.monotonic()+5
    while run["id"] not in client.app.state.manager.processes and time.monotonic()<deadline:
        time.sleep(.05)
    assert client.post(f'/api/runs/{run["id"]}/cancel').status_code==200
    assert finished(client,run["id"])["status"]=="cancelled"
    assert run["id"] not in client.app.state.manager.processes


def test_recovered_stream_retry_can_complete(client):
    sid=session(client)
    run=send(client,sid,"case:retry-recovered").json()
    result=finished(client,run["id"])
    assert result["status"]=="succeeded"
    assert result["error"] is None
    trace=client.get(f'/api/runs/{run["id"]}/trace').json()
    assert any(e['type']=='error' and 'Reconnecting' in e['payload']['message'] for e in trace['events'])


def test_timeout(client):
    sid=session(client)
    run=send(client,sid,"case:hang").json()
    assert finished(client,run["id"])["status"]=="timed_out"


def test_upload_preview_and_path_protection(client,settings):
    sid=session(client)
    response=client.post(f"/api/sessions/{sid}/uploads",files={"file":("data.csv",b"a,b\n1,2\n","text/csv")})
    assert response.status_code==201
    path=response.json()["path"]
    assert client.get(f"/api/sessions/{sid}/file",params={"path":path}).json()["content"]=="a,b\n1,2\n"
    for path in ["../../app.db","/etc/passwd","uploads/../../../app.db",".env"]:
        assert client.get(f"/api/sessions/{sid}/download",params={"path":path}).status_code==400
    secret=settings.data_dir/"outside.txt"
    secret.write_text("secret")
    (settings.data_dir/"sessions"/sid/"workspace/outputs/link.txt").symlink_to(secret)
    assert client.get(f"/api/sessions/{sid}/file",params={"path":"outputs/link.txt"}).status_code==400
    assert client.post(f"/api/sessions/{sid}/uploads",files={"file":("bad.exe",b"x")}).status_code==415


def test_upload_size_limit_and_cleanup(client,settings):
    sid=session(client)
    settings.max_upload=20
    assert client.post(f"/api/sessions/{sid}/uploads",files={"file":("big.txt",b"x"*21)}).status_code==413
    assert client.get(f"/api/sessions/{sid}/files").json()==[]


def test_origin_and_proxy_credential_boundaries(client,settings):
    assert client.post("/api/sessions",json={},headers={"Origin":"https://evil.example"}).status_code==403
    assert client.get("/api/config",headers={"Host":"evil.example"}).status_code==403
    assert client.post("/internal/model/v1/responses",json={}).status_code==401
    assert settings.api_key not in client.get("/api/config").text
    sid=session(client)
    run=send(client,sid).json()
    finished(client,run["id"])
    client.app.state.manager.emit(run["id"],"diagnostic",{"message":"secret="+settings.api_key})
    trace=client.get(f'/api/runs/{run["id"]}/trace').text
    assert settings.api_key not in trace
    assert "[REDACTED]" in trace


def test_sse_replays_after_cursor_without_duplicates(client):
    sid=session(client)
    run=send(client,sid).json()
    finished(client,run["id"])
    events=client.get(f'/api/runs/{run["id"]}/trace').json()["events"]
    cursor=events[1]["id"]
    stream=client.get(f'/api/runs/{run["id"]}/events',headers={"Last-Event-ID":str(cursor)}).text
    ids=[int(line[4:]) for line in stream.splitlines() if line.startswith("id: ")]
    assert ids==[e["id"] for e in events if e["id"]>cursor]
    assert "event: stream.end" in stream


def test_restart_preserves_history_and_marks_interrupted(settings):
    app=create_app(settings)
    store=app.state.store
    s=store.create_session("持久会话")
    run,_=store.enqueue(s["id"],"restart-request","hello")
    store.execute("UPDATE runs SET status='running',started_at=? WHERE id=?",(now(),run["id"]))
    with TestClient(create_app(settings)) as restarted:
        result=restarted.get(f'/api/sessions/{s["id"]}').json()
        assert result["messages"][0]["content"]=="hello"
        assert result["runs"][0]["status"]=="interrupted"


def test_unconfigured_service_does_not_fake_a_run(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        sid=session(client)
        assert send(client,sid).status_code==503
        assert client.get(f"/api/sessions/{sid}").json()["runs"]==[]


def test_proxy_streams_and_adds_only_server_credential(client,settings):
    sid=session(client)
    run=send(client,sid).json()
    finished(client,run['id'])
    observed=[]
    async def upstream(request):
        observed.append(request)
        return httpx.Response(200,headers={"content-type":"text/event-stream"},content=b'data: {"type":"response.completed"}\n\n')
    client.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    client.app.state.manager.tokens["test-proxy-token"]=run['id']
    response=client.post('/internal/model/v1/responses',json={"model":"test","stream":True},headers={"Authorization":"Bearer test-proxy-token"})
    assert response.status_code==200
    assert 'response.completed' in response.text
    assert str(observed[0].url)==settings.base_url+"/responses"
    assert observed[0].headers['authorization']=="Bearer "+settings.api_key
    assert "test-proxy-token" not in str(observed[0].headers)
    assert client.post('/internal/model/v1/not-allowed',headers={"Authorization":"Bearer test-proxy-token"}).status_code==404


def test_cli_receives_proxy_token_but_not_provider_key(client,settings):
    sid=session(client)
    root=client.app.state.manager.prepare_workspace(sid)
    s=client.app.state.store.one('SELECT * FROM sessions WHERE id=?',(sid,))
    args,env=client.app.state.manager.command(s,root,"short-lived-token")
    assert settings.api_key not in str(env)
    assert settings.api_key not in (root/'agent-home/config.toml').read_text()
    assert env['AGENT_SESSION_TOKEN']=="short-lived-token"
    assert args[-1]=='-'


def test_provider_errors_are_readable_and_redacted(client, settings):
    sid=session(client)
    run=send(client,sid).json()
    finished(client,run['id'])
    async def upstream(request):
        return httpx.Response(401,json={'error':{'message':'Invalid key '+settings.api_key}})
    client.app.state.http=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    client.app.state.manager.tokens['error-test-token']=run['id']
    response=client.post('/internal/model/v1/responses',json={},headers={'Authorization':'Bearer error-test-token'})
    assert response.status_code==401
    assert response.json()['error']['message']=='Invalid key [REDACTED]'
    assert settings.api_key not in response.text
    from backend.config import readable_error
    nested=json.dumps({'error':{'message':json.dumps({'error':{'message':'仅支持客户端工具'}})}})
    assert readable_error(nested)=='仅支持客户端工具'
