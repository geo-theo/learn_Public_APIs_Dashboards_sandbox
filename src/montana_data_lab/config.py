from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _database_url() -> str:
    configured = os.getenv("MTDL_DATABASE_URL")
    if configured:
        return configured
    return f"sqlite:///{(PROJECT_ROOT / 'data' / 'montana_data_lab.db').as_posix()}"


@dataclass(frozen=True)
class Settings:
    database_url: str = _database_url()
    http_timeout_seconds: float = float(os.getenv("MTDL_HTTP_TIMEOUT_SECONDS", "20"))
    nws_user_agent: str = os.getenv(
        "MTDL_NWS_USER_AGENT",
        "MontanaPublicDataLab/0.1 (learning-project@example.com)",
    )
    visit_outlier_threshold: int = int(os.getenv("MTDL_VISIT_OUTLIER_THRESHOLD", "10000"))
    host: str = os.getenv("MTDL_HOST", "127.0.0.1")
    port: int = int(os.getenv("MTDL_PORT", "8000"))
    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"


settings = Settings()


def ensure_data_directories() -> None:
    settings.raw_data_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        database_path = Path(settings.database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
