"""
Integration tests for replay safety and idempotency guarantees.

Validates that the ingestion pipeline's deduplication logic holds under:
  - Full batch replay (same batch posted twice)
  - Mixed batches containing new and duplicate event IDs
  - Sequential sensor retries (same single event posted in separate requests)
  - source_ips accounting correctness under duplicate ingest
  - raw_events uniqueness under duplicate ingest

Schema is bootstrapped by tests/conftest.py; rows are reset per test by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    event_id: str | None = None,
    ip: str = "8.8.8.8",
    ts: str = "2025-10-28T18:31:08+00:00",
) -> dict:
    return {
        "id": event_id or str(uuid.uuid4()),
        "ts": ts,
        "source": "cowrie",
        "type": "cowrie.login.failed",
        "data": {"ip": ip, "username": "root", "password": "bad"},
    }


def _ingest(events: list[dict]) -> dict:
    r = client.post("/api/ingest", json={"events": events}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _db_count(sql: str, params: dict | None = None) -> int:
    with get_engine().connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


# ---------------------------------------------------------------------------
# Full batch replay
# ---------------------------------------------------------------------------


def test_replay_full_batch_accepted_once():
    events = [_event() for _ in range(3)]
    r1 = _ingest(events)
    r2 = _ingest(events)

    assert r1["accepted"] == 3
    assert r2["accepted"] == 0
    assert r2["duplicate"] == 3
    assert r2["errors"] == []


def test_replay_no_duplicate_raw_event_rows():
    eid = str(uuid.uuid4())
    event = _event(event_id=eid)
    _ingest([event])
    _ingest([event])

    count = _db_count("SELECT COUNT(*) FROM raw_events WHERE id = :id", {"id": eid})
    assert count == 1


def test_replay_no_duplicate_event_rows():
    eid = str(uuid.uuid4())
    event = _event(event_id=eid)
    _ingest([event])
    _ingest([event])

    count = _db_count("SELECT COUNT(*) FROM events WHERE id = :id", {"id": eid})
    assert count == 1


# ---------------------------------------------------------------------------
# source_ips counter correctness under replay
# ---------------------------------------------------------------------------


def test_replay_source_ip_event_count_not_incremented():
    """Duplicate ingest must not bump source_ips.event_count."""
    event = _event(ip="1.2.3.4")
    _ingest([event])
    _ingest([event])

    count = _db_count("SELECT event_count FROM source_ips WHERE ip = '1.2.3.4'")
    assert count == 1


def test_replay_source_ip_count_increments_for_new_events():
    """Two distinct events from the same IP must produce event_count=2."""
    _ingest([_event(ip="1.2.3.4")])
    _ingest([_event(ip="1.2.3.4")])

    count = _db_count("SELECT event_count FROM source_ips WHERE ip = '1.2.3.4'")
    assert count == 2


# ---------------------------------------------------------------------------
# Mixed batch: new + duplicate IDs
# ---------------------------------------------------------------------------


def test_mixed_batch_new_and_duplicate_accounting():
    """Batch containing previously-ingested IDs: only new events are accepted."""
    existing = [_event() for _ in range(2)]
    _ingest(existing)

    new_events = [_event() for _ in range(3)]
    receipt = _ingest(existing + new_events)

    assert receipt["accepted"] == 3
    assert receipt["duplicate"] == 2
    assert receipt["errors"] == []


def test_mixed_batch_does_not_create_extra_rows():
    existing = [_event() for _ in range(2)]
    _ingest(existing)
    _ingest(existing + [_event()])

    total = _db_count("SELECT COUNT(*) FROM events")
    assert total == 3  # 2 from first batch + 1 new from second


# ---------------------------------------------------------------------------
# Sequential sensor retry (same event, separate requests)
# ---------------------------------------------------------------------------


def test_sequential_retry_counted_as_duplicate():
    """Sensor posting the same event in two sequential requests: second is duplicate."""
    event = _event(event_id=str(uuid.uuid4()))

    r1 = _ingest([event])
    r2 = _ingest([event])

    assert r1["accepted"] == 1
    assert r2["duplicate"] == 1
    assert r2["accepted"] == 0


def test_sequential_retry_total_row_count_unchanged():
    event = _event(event_id=str(uuid.uuid4()))
    _ingest([event])
    _ingest([event])
    _ingest([event])

    count = _db_count("SELECT COUNT(*) FROM raw_events WHERE id = :id", {"id": event["id"]})
    assert count == 1


# ---------------------------------------------------------------------------
# Intra-batch duplicate (same ID appears twice in one request)
# ---------------------------------------------------------------------------


def test_intra_batch_duplicate_id_counted_correctly():
    """Two entries with the same ID in one batch: first accepted, second duplicate."""
    eid = str(uuid.uuid4())
    receipt = _ingest([_event(event_id=eid), _event(event_id=eid)])

    assert receipt["accepted"] == 1
    assert receipt["duplicate"] == 1
    assert receipt["errors"] == []


def test_intra_batch_duplicate_produces_one_row():
    eid = str(uuid.uuid4())
    _ingest([_event(event_id=eid), _event(event_id=eid)])

    count = _db_count("SELECT COUNT(*) FROM raw_events WHERE id = :id", {"id": eid})
    assert count == 1
