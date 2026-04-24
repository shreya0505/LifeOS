"""Shared test fixtures for QuestLog."""

from __future__ import annotations

import os
import tempfile

import pytest
import pytest_asyncio
import aiosqlite

from web.db import migrate


@pytest.fixture(autouse=True)
def _use_tmp_db(tmp_path, monkeypatch):
    """Point QUESTLOG_DB at a temp file for every test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("QUESTLOG_DB", db_path)
    monkeypatch.setenv("SYNC_ENABLED", "false")


@pytest_asyncio.fixture
async def db(tmp_path):
    """Yield a migrated aiosqlite connection."""
    db_path = str(tmp_path / "test.db")
    os.environ["QUESTLOG_DB"] = db_path
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await migrate(conn)
    yield conn
    await conn.close()


@pytest_asyncio.fixture
async def client(db):
    """Yield an httpx AsyncClient wired to the FastAPI app."""
    # Import here so QUESTLOG_DB env is already set
    from web.app import app
    from httpx import AsyncClient, ASGITransport

    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
