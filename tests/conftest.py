import os
import pathlib

import pytest


def pytest_sessionstart(session):
    # Create a writable storage dir and point EVENTS_PATH at it
    storage = pathlib.Path("./storage").resolve()
    storage.mkdir(parents=True, exist_ok=True)
    events_path = storage / "test-events.jsonl"
    os.environ["EVENTS_PATH"] = str(events_path)


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
