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
        conn.execute(text("DELETE FROM ai_audit_log"))
        conn.execute(text("DELETE FROM ai_outputs"))
        conn.execute(text("DELETE FROM processing_jobs"))
        conn.execute(text("DELETE FROM fingerprint_history"))
        conn.execute(text("DELETE FROM behavioral_fingerprints"))
        conn.execute(text("DELETE FROM campaign_tags"))
        conn.execute(text("DELETE FROM campaign_observations"))
        conn.execute(text("DELETE FROM campaign_members"))
        conn.execute(text("DELETE FROM behavioral_alerts"))
        conn.execute(text("DELETE FROM campaign_weight_profiles"))
        conn.execute(text("DELETE FROM campaign_lineage"))
        conn.execute(text("DELETE FROM actor_profiles"))
        conn.execute(text("DELETE FROM campaigns"))
        conn.execute(text("DELETE FROM events"))
        conn.execute(text("DELETE FROM raw_events"))
        conn.execute(text("DELETE FROM source_ips"))
        conn.execute(text("DELETE FROM audit_log"))
        conn.commit()
