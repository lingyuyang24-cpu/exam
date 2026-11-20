import asyncio
import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Settings, readable_error
from .db import Store, now, uid
from .files import UPLOAD_EXTENSIONS, safe_path, workspace_files
from .runner import RunManager, TERMINAL


class SessionInput(BaseModel):
    title: str = Field(default="新会话", min_length=1, max_length=80)


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=32000)
    request_id: str = Field(min_length=8, max_length=100)


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir / "app.db")
    manager = RunManager(settings, store)

    @asynccontextmanager
    async def lifespan(app):
        app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=20), follow_redirects=False)
        await manager.start()
        yield
        await manager.close()
        await app.state.http.aclose()

    app = FastAPI(title="Agent Desk", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.manager, app.state.settings = store, manager, settings

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.url.hostname not in {"localhost", "127.0.0.1", "::1", "testserver"}:
            return JSONResponse({"detail": "此版本仅支持本机访问。"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.url.netloc:
            return JSONResponse({"detail": "不允许跨站请求。"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def session_or_404(sid):
        session = store.one("SELECT * FROM sessions WHERE id=?", (sid,))
        if not session or session["deleted_at"]:
            raise HTTPException(404, "会话不存在")
        return session

    def run_or_404(rid):
        run = store.one("SELECT * FROM runs WHERE id=?", (rid,))
        if not run:
            raise HTTPException(404, "任务不存在")
        session_or_404(run["session_id"])
        return run

    def workspace(sid):
        session_or_404(sid)
        return manager.session_root(sid) / "workspace"

    def resolve_file(sid, path):
        try:
            return safe_path(workspace(sid), path)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except FileNotFoundError:
            raise HTTPException(404, "文件不存在")

    @app.get("/healthz")
    async def health():
        store.one("SELECT 1")
        return {"status": "ok", "configured": settings.configured, "cli_available": bool(shutil.which(settings.cli))}

    @app.get("/api/config")
    async def config():
        return {"configured": settings.configured, "model": settings.model, "engine": "Codex CLI",
                "cli_available": bool(shutil.which(settings.cli)), "concurrency": settings.concurrency,
                "timeout_seconds": settings.timeout, "max_upload_bytes": settings.max_upload,
                "upload_extensions": sorted(UPLOAD_EXTENSIONS), "sandbox": settings.sandbox}

    @app.get("/api/sessions")
    async def sessions(deleted: bool = False):
        return store.sessions(deleted=deleted)

    @app.post("/api/sessions", status_code=201)
    async def create_session(data: SessionInput):
        session = store.create_session(data.title.strip() or "新会话")
        manager.prepare_workspace(session["id"])
        return session

    @app.patch("/api/sessions/{sid}")
    async def rename_session(sid: str, data: SessionInput):
        session_or_404(sid)
        store.execute("UPDATE sessions SET title=?,updated_at=? WHERE id=?", (data.title.strip() or "新会话", now(), sid))
        return session_or_404(sid)

    def change_deleted(sid, deleted):
        try:
            return store.set_session_deleted(sid, deleted)
        except LookupError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.delete("/api/sessions/{sid}")
    async def delete_session(sid: str):
        return change_deleted(sid, True)

    @app.post("/api/sessions/{sid}/restore")
    async def restore_session(sid: str):
        return change_deleted(sid, False)

    @app.get("/api/sessions/{sid}")
    async def session_detail(sid: str):
        return {"session": session_or_404(sid),
                "messages": store.all("SELECT * FROM messages WHERE session_id=? ORDER BY created_at", (sid,)),
                "runs": store.all("SELECT * FROM runs WHERE session_id=? ORDER BY created_at", (sid,)),
                "artifacts": store.all("SELECT * FROM artifacts WHERE session_id=? ORDER BY created_at DESC", (sid,))}

    @app.post("/api/sessions/{sid}/messages", status_code=202)
    async def send_message(sid: str, data: MessageInput):
        session_or_404(sid)
        if not data.content.strip():
            raise HTTPException(422, "消息不能为空")
        if not settings.configured:
            raise HTTPException(503, "模型 API 尚未配置。请在 .env 填写地址与密钥，然后重启服务。")
        if not shutil.which(settings.cli):
            raise HTTPException(503, "Agent CLI 未安装，请使用 Docker 启动或安装指定版本的 Codex CLI。")
        try:
            run, created = store.enqueue(sid, data.request_id, data.content.strip())
        except LookupError as exc:
            raise HTTPException(404, str(exc))
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if created:
            manager.emit(run["id"], "run.status", {"status": "queued"})
        return run

    @app.get("/api/runs/{rid}")
    async def run_detail(rid: str):
        return run_or_404(rid)

    @app.get("/api/runs/{rid}/events")
    async def events(rid: str, request: Request, after: int = 0):
        run_or_404(rid)
        try:
            cursor = max(0, after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise HTTPException(422, "事件游标格式不正确")

        async def stream():
            nonlocal cursor
            idle = 0
            while not await request.is_disconnected():
                batch = store.events(rid, cursor)
                for event in batch:
                    cursor = event["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if not batch and run_or_404(rid)["status"] in TERMINAL:
                    yield 'event: stream.end\ndata: {}\n\n'
                    return
                idle += 1
                if idle % 30 == 0:
                    yield ': heartbeat\n\n'
                if len(batch) < 250:
                    await asyncio.sleep(0.35)
        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/runs/{rid}/trace")
    async def trace(rid: str):
        run = run_or_404(rid)
        events = store.all("SELECT * FROM events WHERE run_id=? ORDER BY id", (rid,))
        for event in events:
            event["payload"] = json.loads(event["payload"])
        content = settings.redact(json.dumps({"run": run, "events": events}, ensure_ascii=False, indent=2))
        return StreamingResponse(iter([content]), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="run-{rid}.json"'})

    @app.post("/api/runs/{rid}/cancel")
    async def cancel(rid: str):
        await manager.cancel(run_or_404(rid))
        return run_or_404(rid)

    @app.get("/api/sessions/{sid}/files")
    async def files(sid: str):
        return workspace_files(workspace(sid))

    @app.post("/api/sessions/{sid}/uploads", status_code=201)
    async def upload(sid: str, file: UploadFile = File(...)):
        root = workspace(sid)
        if store.one("SELECT id FROM runs WHERE session_id=? AND status IN ('queued','running')", (sid,)):
            raise HTTPException(409, "请在本轮任务完成后上传新材料。")
        name = re.sub(r"[^\w.() -]", "_", Path(file.filename or "file.txt").name)[:120].strip('. ')
        if Path(name).suffix.lower() not in UPLOAD_EXTENSIONS:
            raise HTTPException(415, "暂不支持该格式，请上传文本、CSV、JSON 或代码文件。")
        existing = workspace_files(root)
        if len(existing) >= 1000 or sum(f["size"] for f in existing if f["category"] == "input") >= 100*1024*1024:
            raise HTTPException(413, "当前会话材料容量已达到上限。")
        relative = f"uploads/{uid()[:8]}_{name}"
        dest = safe_path(root, relative, must_exist=False)
        size = 0
        try:
            with dest.open("xb") as output:
                while chunk := await file.read(64*1024):
                    size += len(chunk)
                    if size > settings.max_upload:
                        raise HTTPException(413, "文件超过 10 MB 限制。")
                    output.write(chunk)
        except BaseException:
            dest.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        store.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), sid))
        return {"name": name, "path": relative, "size": size}

    @app.get("/api/sessions/{sid}/file")
    async def preview(sid: str, path: str):
        file = resolve_file(sid, path)
        with file.open("rb") as src:
            data = src.read(256*1024 + 1)
        if b"\x00" in data:
            raise HTTPException(415, "二进制文件请下载后查看。")
        return {"path": path, "content": data[:256*1024].decode("utf-8", errors="replace"), "truncated": len(data)>256*1024}

    @app.get("/api/sessions/{sid}/download")
    async def download_file(sid: str, path: str):
        file = resolve_file(sid, path)
        name = re.sub(r"^[0-9a-f]{8}_", "", file.name) if Path(path).parts[0] == "uploads" else file.name
        return FileResponse(file, filename=name, media_type="application/octet-stream")

    @app.get("/api/artifacts/{aid}/download")
    async def download_artifact(aid: str):
        artifact = store.one("SELECT * FROM artifacts WHERE id=?", (aid,))
        if not artifact:
            raise HTTPException(404, "成果不存在")
        session_or_404(artifact["session_id"])
        try:
            file = safe_path(settings.data_dir, artifact["relative_path"])
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "成果文件不存在")
        return FileResponse(file, filename=artifact["name"], media_type="application/zip")

    @app.post("/internal/model/v1/{endpoint:path}")
    async def inference_proxy(endpoint: str, request: Request):
        # A run-scoped token lets the CLI make model requests without receiving
        # the upstream credential. This is not a hostile-code isolation boundary.
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        rid = manager.tokens.get(token)
        if not rid:
            raise HTTPException(401, "Invalid run token")
        if endpoint not in {"responses", "responses/compact"}:
            raise HTTPException(404, "Unsupported model endpoint")
        body = await request.body()
        if len(body) > 20*1024*1024:
            raise HTTPException(413, "Model request is too large")
        if not request.headers.get("content-encoding"):
            try:
                payload = json.loads(body)
                manager.emit(rid, "provider.request", {"endpoint": endpoint, "model": payload.get("model"),
                    "tool_types": sorted({tool.get("type", "unknown") for tool in payload.get("tools", [])}),
                    "tool_count": len(payload.get("tools", []))})
            except (ValueError, TypeError, AttributeError):
                pass
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        for name in ["openai-beta", "x-codex-turn-metadata", "content-encoding"]:
            if value := request.headers.get(name):
                headers[name] = value
        try:
            upstream_request = app.state.http.build_request("POST", f"{settings.base_url}/{endpoint}", content=body, headers=headers)
            response = await app.state.http.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            manager.emit(rid, "error", {"message": "无法连接模型服务：" + str(exc)[:500]})
            raise HTTPException(502, "Upstream model connection failed")
        if response.status_code >= 400:
            content = (await response.aread()).decode(errors="replace")
            await response.aclose()
            message = settings.redact(readable_error(content))[:2000]
            manager.emit(rid, "error", {"message": f"模型服务返回 HTTP {response.status_code}：" + message})
            return JSONResponse({"error": {"message": message, "type": "upstream_error"}}, status_code=response.status_code)

        async def forward():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
        return StreamingResponse(forward(), status_code=response.status_code,
                                 media_type=response.headers.get("content-type", "application/json"))

    frontend = Path(os.getenv("FRONTEND_DIST", str(Path(__file__).parent.parent / "frontend" / "dist")))
    if frontend.is_dir():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
