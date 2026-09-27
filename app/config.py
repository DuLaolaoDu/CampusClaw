"""Environment-driven app configuration."""
from __future__ import annotations

import os


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise ValueError(f"Required env var {name!r} is not set")
    return val.strip()


class Config:
    # Flask session signing key — MUST be provided
    APP_SECRET: str = _require("APP_SECRET")

    # SQLite path (defaults to current dir)
    DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "campusclaw.db")

    # Uploaded files dir — defaults to <db dir>/uploads so it lands in the existing volume
    UPLOAD_DIR: str = os.environ.get(
        "UPLOAD_DIR",
        os.path.join(os.path.dirname(DATABASE_PATH) or ".", "uploads"),
    )

    # File upload limits
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: frozenset = frozenset({"txt", "md", "pdf"})

    FLASK_ENV: str = os.environ.get("FLASK_ENV", "production")
