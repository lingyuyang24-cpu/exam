"""Bounded file access and immutable, per-run artifact snapshots."""
import hashlib
import json
import os
import re
import zipfile
from pathlib import Path

from .db import now, uid

UPLOAD_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts", ".html", ".css"}
EXCLUDED = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".codex", "agent-home"}


def safe_path(root: Path, relative: str, must_exist=True):
    if not relative or "\x00" in relative or Path(relative).is_absolute():
        raise ValueError("无效文件路径")
    parts = Path(relative).parts
    if any(p in {"..", "."} or p.startswith(".") for p in parts):
        raise ValueError("不允许访问该路径")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("不允许访问符号链接")
    resolved = current.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("文件不属于当前工作区")
    if must_exist and not resolved.is_file():
        raise FileNotFoundError(relative)
    return resolved


def workspace_files(root: Path, limit=1000):
    result = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith('.') and not (Path(base)/d).is_symlink())
        for name in sorted(files):
            if name.startswith('.') or name in {"AGENTS.md"}:
                continue
            path = Path(base)/name
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            display_name = re.sub(r"^[0-9a-f]{8}_", "", name) if path.relative_to(root).parts[0] == "uploads" else name
            result.append({"path": str(path.relative_to(root)), "name": display_name, "size": stat.st_size,
                           "modified_at": stat.st_mtime, "category": "input" if path.relative_to(root).parts[0] == "uploads" else "output"})
            if len(result) >= limit:
                return result
    return result


def snapshot(settings, store, run, partial):
    root = settings.data_dir / "sessions" / run["session_id"]
    workspace = root / "workspace"
    files = [f for f in workspace_files(workspace) if f["category"] == "output"]
    if not files:
        return None
    dest = root / "artifacts" / run["id"]
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "成果.zip"
    manifest, skipped, total = [], [], 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for entry in files:
            if total + entry["size"] > settings.max_artifact:
                skipped.append(entry["path"])
                continue
            path = safe_path(workspace, entry["path"])
            data = path.read_bytes()
            if total + len(data) > settings.max_artifact:
                skipped.append(entry["path"])
                continue
            total += len(data)
            zipped.writestr(entry["path"], data)
            manifest.append({"path": entry["path"], "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        zipped.writestr("artifact-manifest.json", json.dumps({"run_id": run["id"], "partial": partial,
                           "files": manifest, "skipped": skipped}, ensure_ascii=False, indent=2))
    artifact = {"id": uid(), "session_id": run["session_id"], "run_id": run["id"], "name": "成果.zip",
                "relative_path": str(archive.relative_to(settings.data_dir)), "size": archive.stat().st_size,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "partial": int(partial), "created_at": now()}
    store.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)", tuple(artifact.values()))
    return {**artifact, "files_count": len(manifest), "skipped": skipped}
