from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("MONEKI_DB_PATH", str(ROOT_DIR / "backend" / "data" / "moneki.sqlite3")))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "MONEKI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
