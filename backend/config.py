"""Server-owned configuration. Secrets are never returned through public APIs."""
import os
import json
from dataclasses import dataclass
from pathlib import Path


def readable_error(value):
    """Unwrap provider/CLI JSON envelopes into a useful, bounded error message."""
    for _ in range(20):
        if isinstance(value, dict):
            if "error" in value:
                value = value["error"]
            elif "message" in value:
                value = value["message"]
            else:
                return json.dumps(value, ensure_ascii=False)[:4000]
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                return value[:4000]
            if parsed == value:
                return value[:4000]
            value = parsed
        else:
            return str(value)[:4000]
    return str(value)[:4000]


@dataclass
class Settings:
    data_dir: Path
    api_key: str = ""
    base_url: str = ""
    model: str = "linext-5.3-luna"
    cli: str = "codex"
    timeout: int = 1200
    concurrency: int = 2
    port: int = 8080
    sandbox: str = "workspace-write"
    max_upload: int = 10 * 1024 * 1024
    max_artifact: int = 50 * 1024 * 1024

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", "./data")).resolve(),
            api_key=os.getenv("AGENT_API_KEY", ""),
            base_url=os.getenv("AGENT_BASE_URL", "").rstrip("/"),
            model=os.getenv("AGENT_MODEL", "linext-5.3-luna"),
            cli=os.getenv("AGENT_CLI", "codex"),
            timeout=max(5, int(os.getenv("TASK_TIMEOUT_SECONDS", "1200"))),
            concurrency=max(1, min(4, int(os.getenv("MAX_CONCURRENT_RUNS", "2")))),
            port=int(os.getenv("PORT", "8080")),
            sandbox=os.getenv("AGENT_SANDBOX", "workspace-write"),
        )

    @property
    def configured(self):
        return bool(self.api_key and self.base_url and self.model)

    def redact(self, text: str) -> str:
        return text.replace(self.api_key, "[REDACTED]") if self.api_key else text
