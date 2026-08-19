from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_local_env() -> None:
    """Load simple KEY=VALUE entries without adding a runtime dotenv dependency."""
    env_path = ROOT_DIR / "backend" / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()

_db_value = Path(os.getenv("MONEKI_DB_PATH", str(ROOT_DIR / "backend" / "data" / "moneki.sqlite3")))
DB_PATH = _db_value if _db_value.is_absolute() else ROOT_DIR / _db_value
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "MONEKI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    ).split(",")
    if origin.strip()
]
AI_PROVIDER = os.getenv("MONEKI_AI_PROVIDER", "mock").lower()
AI_API_KEY = os.getenv("MONEKI_AI_API_KEY", "")
AI_BASE_URL = os.getenv("MONEKI_AI_BASE_URL", "https://api.deepseek.com").rstrip("/")
AI_MODEL = os.getenv("MONEKI_AI_MODEL", "deepseek-chat")
AI_TIMEOUT_SECONDS = float(os.getenv("MONEKI_AI_TIMEOUT_SECONDS", "20"))
