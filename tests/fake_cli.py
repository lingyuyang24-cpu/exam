#!/usr/bin/env python3
"""TEST DOUBLE ONLY: tests process/event handling without calling a model API."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def emit(kind, **data):
    print(json.dumps({"type": kind, **data}), flush=True)


prompt = sys.stdin.read()
if "case:hang" in prompt:
    # A descendant process lets the cancellation test check process-group cleanup.
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    emit("thread.started", thread_id="test-thread")
    time.sleep(60)
elif "case:failure" in prompt:
    emit("thread.started", thread_id="test-thread")
    emit("turn.failed", error={"message": "Synthetic provider failure (test double)"})
    sys.exit(2)
elif "case:missing-completion" in prompt:
    emit("thread.started", thread_id="test-thread")
else:
    assert "AGENT_API_KEY" not in os.environ, "Upstream credentials leaked into child"
    emit("thread.started", thread_id="test-thread")
    emit("item.started", item={"id":"cmd-1","type":"command_execution","command":"python process-test.py","status":"in_progress"})
    if "case:slow" in prompt:
        time.sleep(1)
    output = Path("outputs/result.txt")
    output.write_text("continued" if "resume" in sys.argv else "first run", encoding="utf-8")
    emit("item.completed", item={"id":"cmd-1","type":"command_execution","command":"python process-test.py","status":"completed","exit_code":0,"aggregated_output":"TEST DOUBLE: lifecycle fixture"})
    emit("item.completed", item={"id":"reply-1","type":"agent_message","text":"Test fixture finished (not real model output)."})
    emit("turn.completed", usage={"input_tokens":10,"output_tokens":5})
