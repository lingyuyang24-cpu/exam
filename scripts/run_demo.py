"""Run and record REAL Agent tasks via the application API. No fixture mode.

Usage: python scripts/run_demo.py --url http://127.0.0.1:8080
Rerunning with the same output directory resumes collection without duplicating runs.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from demo.verify_sales import totals
from decimal import Decimal
import csv
import io
import zipfile

PROMPTS = {
    "code_1": "请在 project 目录开发一个 Python CSV 数据质量检查工具。支持输入 CSV 路径，检查每列缺失值和完整重复行（除首次出现外的重复行数），输出 JSON 报告。提供 README 和至少 4 个 unittest 测试，实际运行测试。只使用 Python 标准库，不安装依赖。",
    "work_1": "请分析 uploads 中的销售数据和会议记录。第一版按全部订单统计，以数量乘单价为订单金额。在 outputs 生成 report.md 和 summary.csv。CSV 列固定为 region,total_sales，按区域汇总金额。报告包含区域销售额、产品排名、各订单状态金额、会议待办及待确认问题，注明材料来源与统计口径。使用 Python 计算并保留分析脚本，不要编造利润或取消原因。",
    "code_2": "在刚才的工具基础上增加 --dedupe-output 参数，把去重结果写入指定新文件，保留首个出现的完整行，保持原始输入不变。补充测试并运行全部测试，在回复中说明实际测试结果。",
    "work_2": "将 report.md 和 summary.csv 改为只统计已完成订单，CSV 仍为 region,total_sales 两列。报告压缩为一页管理层摘要，保留总金额、区域金额、重要结论、负责人和期限。实际重新运行分析脚本并验证关键数字。",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "real")
    parser.add_argument("--wait-seconds", type=int, default=1300)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / "demo-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"sessions": {}, "runs": {}, "source": "real application API / real Codex CLI"}
    client = httpx.Client(base_url=args.url, timeout=30)

    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def save():
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    config = request("GET", "/api/config")
    if not config["configured"] or not config["cli_available"]:
        raise SystemExit("真实 API 或 CLI 尚未配置，未创建演示任务。")
    state["config"] = config
    for key, title in [("code", "CSV 质检工具 · 开发演示"), ("work", "十月销售复盘 · 材料分析")]:
        if key not in state["sessions"]:
            state["sessions"][key] = request("POST", "/api/sessions", json={"title": title})["id"]
            save()
    if not state.get("materials_uploaded"):
        for filename in ["sales.csv", "meeting_notes.md"]:
            with (ROOT / "demo" / "inputs" / filename).open("rb") as file:
                request("POST", f'/api/sessions/{state["sessions"]["work"]}/uploads', files={"file": (filename, file)})
        state["materials_uploaded"] = True
        save()

    for round_number in [1, 2]:
        tags = [f"code_{round_number}", f"work_{round_number}"]
        for tag in tags:
            if tag not in state["runs"]:
                sid = state["sessions"][tag.split("_")[0]]
                state["runs"][tag] = request("POST", f"/api/sessions/{sid}/messages",
                    json={"content": PROMPTS[tag], "request_id": f"recorded-demo-{tag}"})
                save()
                print(f'{tag}: submitted {state["runs"][tag]["id"]}', flush=True)
        deadline = time.monotonic() + args.wait_seconds
        previous = {}
        while True:
            pending = False
            for tag in tags:
                run = request("GET", f'/api/runs/{state["runs"][tag]["id"]}')
                state["runs"][tag] = run
                if previous.get(tag) != run["status"]:
                    print(f'{tag}: {run["status"]}', flush=True)
                    previous[tag] = run["status"]
                pending |= run["status"] in {"queued", "running"}
            save()
            if not pending:
                break
            if time.monotonic() > deadline:
                raise SystemExit("等待超时。应用任务仍按服务端时限运行，可用相同命令继续收集。")
            time.sleep(2)
        for tag in tags:
            run = state["runs"][tag]
            trace = request("GET", f'/api/runs/{run["id"]}/trace')
            (output / f"{tag}-trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2))
            session = request("GET", f'/api/sessions/{run["session_id"]}')
            (output / f"{tag}-session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2))
            if run["status"] != "succeeded":
                raise SystemExit(f'{tag} 未成功：{run.get("error")}; 执行记录已保存。')
            artifacts = [a for a in session["artifacts"] if a["run_id"] == run["id"]]
            if not artifacts:
                raise SystemExit(f"{tag} 没有成果快照，请检查日志。")
            artifact = artifacts[0]
            downloaded = client.get(f'/api/artifacts/{artifact["id"]}/download')
            downloaded.raise_for_status()
            assert hashlib.sha256(downloaded.content).hexdigest() == artifact["sha256"]
            (output / f"{tag}-artifacts.zip").write_bytes(downloaded.content)
            if tag.startswith("work"):
                expected = totals(ROOT / "demo/inputs/sales.csv", completed_only=round_number==2)
                with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
                    actual = {r["region"]: r["total_sales"] for r in csv.DictReader(io.StringIO(archive.read("outputs/summary.csv").decode("utf-8-sig")))}
                passed = set(actual) == set(expected) and all(Decimal(actual[k]) == Decimal(v) for k,v in expected.items())
                verification = {"passed": passed, "expected": expected, "actual": actual, "method": "independent Python Decimal aggregation"}
                (output / f"{tag}-verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2))
                if not passed:
                    raise SystemExit(f"{tag} 汇总数值验证未通过，证据已保留。")
    print(f"四轮真实执行及销售数字比对完成。证据目录：{output}")


if __name__ == "__main__":
    main()
