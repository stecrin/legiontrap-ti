"""
Integration test fixtures.

The schema is bootstrapped once per session by tests/conftest.py.
This conftest adds a per-test DB reset so ingest tests don't accumulate
state that leaks into stats/ordering assertions.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.connection import get_engine


@pytest.fixture(autouse=True)
def reset_db_rows():
    """Truncate all data tables before each integration test."""
    yield
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM events"))
        conn.execute(text("DELETE FROM raw_events"))
        conn.execute(text("DELETE FROM source_ips"))
        conn.execute(text("DELETE FROM audit_log"))
        conn.commit()
