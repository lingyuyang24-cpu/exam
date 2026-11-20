"""Server-owned configuration. Secrets are never returned through public APIs."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path
    api_key: str = ""
    base_url: str = ""
    model: str = "linext-5.3-luna"
    cli: str = "codex"
    timeout: int = 600
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
            timeout=max(5, int(os.getenv("TASK_TIMEOUT_SECONDS", "600"))),
            concurrency=max(1, min(4, int(os.getenv("MAX_CONCURRENT_RUNS", "2")))),
            port=int(os.getenv("PORT", "8080")),
            sandbox=os.getenv("AGENT_SANDBOX", "workspace-write"),
        )

    @property
    def configured(self):
        return bool(self.api_key and self.base_url and self.model)

    def redact(self, text: str) -> str:
        return text.replace(self.api_key, "[REDACTED]") if self.api_key else text
