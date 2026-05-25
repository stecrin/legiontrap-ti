import os
import pathlib

import pytest


def pytest_sessionstart(session):
    # Create a writable storage dir and point EVENTS_PATH at it
    storage = pathlib.Path("./storage").resolve()
    storage.mkdir(parents=True, exist_ok=True)
    events_path = storage / "test-events.jsonl"
    os.environ["EVENTS_PATH"] = str(events_path)

    # Bootstrap the in-memory SQLite schema so migrated route handlers
    # (stats, events, ingest) have valid tables. DB_PATH=:memory: is set in
    # pytest.ini; alembic upgrade head cannot run against :memory:.
    from app.db.connection import create_all_tables, get_engine

    create_all_tables(get_engine())


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset in-memory rate limit storage before each test.

    Prevents state bleed between tests — without this, login tests that share
    the 'testclient' IP bucket would exhaust the per-minute limit and cause
    unrelated tests to receive 429.
    """
    from app.limiter import limiter

    limiter._storage.reset()
    yield
