from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.config import Settings, get_settings
from app.db.engine import build_engine, reset_engines
from app.db.models import create_all
from app.security.ratelimit import limiter


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point every test at a throwaway database and a fake key."""
    monkeypatch.setenv("FINEDGE_API_KEY", "test_key_not_a_real_credential")
    # The suite drives one client hard from a single address, which is exactly
    # what the limiter exists to stop. Off by default; test_ratelimit.py turns
    # it on deliberately.
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("STOCKLENS_DB_PATH", str(tmp_path / "core.db"))
    monkeypatch.setenv("STOCKLENS_RAW_DB_PATH", str(tmp_path / "raw.db"))
    get_settings.cache_clear()
    reset_engines()
    limiter.reset()
    yield
    get_settings.cache_clear()
    reset_engines()


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def engines(tmp_path: Path) -> tuple[Engine, Engine]:
    core = build_engine(tmp_path / "core_direct.db")
    raw = build_engine(tmp_path / "raw_direct.db")
    create_all(core, raw)
    return core, raw


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


os.environ.setdefault("ENVIRONMENT", "test")
