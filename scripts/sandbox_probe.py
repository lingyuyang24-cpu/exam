"""Executed INSIDE the CLI sandbox; proves allowed writes and blocked writes.

Container example (after creating /data/sandbox-probe):
codex sandbox linux --full-auto -- python /app/scripts/sandbox_probe.py
"""
from pathlib import Path

Path("allowed.txt").write_text("workspace-write probe")
print("workspace write: allowed")
try:
    Path("/home/agent/outside-probe.txt").write_text("must be blocked")
except PermissionError:
    print("outside workspace write: blocked")
else:
    raise RuntimeError("Sandbox failed: writing outside the workspace was not blocked")
