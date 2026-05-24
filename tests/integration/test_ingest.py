"""
Integration tests for POST /api/ingest.

These tests hit the full stack: HTTP → router → repository → in-memory SQLite.
Schema is bootstrapped by tests/conftest.py; rows are reset per test by
tests/integration/conftest.py.
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


def _cowrie_event(
    event_id: str | None = None,
    ts: str = "2025-10-28T18:31:08+00:00",
    event_type: str = "cowrie.login.failed",
    ip: str = "203.0.113.2",
    password: str = "badpass",
) -> dict:
    return {
        "id": event_id or str(uuid.uuid4()),
        "ts": ts,
        "source": "cowrie",
        "type": event_type,
        "data": {"ip": ip, "username": "root", "password": password},
    }


def _ingest(events: list[dict]) -> dict:
    r = client.post("/api/ingest", json={"events": events}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()


def _db_query(sql: str, params: dict | None = None):
    with get_engine().connect() as conn:
        return conn.execute(text(sql), params or {}).fetchall()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_ingest_requires_api_key():
    r = client.post("/api/ingest", json={"events": [_cowrie_event()]})
    assert r.status_code == 401


def test_ingest_wrong_key_rejected():
    r = client.post(
        "/api/ingest",
        json={"events": [_cowrie_event()]},
        headers={"x-api-key": "wrong-key"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Happy path — single event
# ---------------------------------------------------------------------------


def test_ingest_single_cowrie_event_accepted():
    receipt = _ingest([_cowrie_event()])
    assert receipt["accepted"] == 1
    assert receipt["rejected"] == 0
    assert receipt["duplicate"] == 0
    assert receipt["errors"] == []
    assert receipt["batch_id"]


def test_ingest_writes_to_raw_events_table():
    eid = str(uuid.uuid4())
    _ingest([_cowrie_event(event_id=eid)])
    rows = _db_query("SELECT id, source FROM raw_events WHERE id = :id", {"id": eid})
    assert len(rows) == 1
    assert rows[0][1] == "cowrie"


def test_ingest_writes_to_events_table():
    eid = str(uuid.uuid4())
    _ingest([_cowrie_event(event_id=eid)])
    rows = _db_query("SELECT id, event_type FROM events WHERE id = :id", {"id": eid})
    assert len(rows) == 1
    assert rows[0][1] == "auth_failed"


def test_ingest_extracts_nested_ip():
    """data.ip (Cowrie nested format) must be extracted to events.src_ip."""
    eid = str(uuid.uuid4())
    _ingest([_cowrie_event(event_id=eid, ip="1.2.3.4")])
    rows = _db_query("SELECT src_ip FROM events WHERE id = :id", {"id": eid})
    assert rows[0][0] == "1.2.3.4"


def test_ingest_upserts_source_ip():
    _ingest([_cowrie_event(ip="8.8.8.8")])
    rows = _db_query("SELECT ip, event_count FROM source_ips WHERE ip = '8.8.8.8'")
    assert len(rows) == 1
    assert rows[0][1] == 1


# ---------------------------------------------------------------------------
# Security — sensitive fields must not leak into events table
# ---------------------------------------------------------------------------


def test_password_not_in_events_table():
    """data.password is attacker-controlled and must never reach the events table."""
    eid = str(uuid.uuid4())
    _ingest([_cowrie_event(event_id=eid, password="SHOULD_NOT_BE_STORED")])

    # The events table has no password column — verify the row was inserted
    # and the raw_json in raw_events is the only place the password appears.
    events_rows = _db_query("SELECT * FROM events WHERE id = :id", {"id": eid})
    assert len(events_rows) == 1

    raw_rows = _db_query("SELECT raw_json FROM raw_events WHERE id = :id", {"id": eid})
    assert len(raw_rows) == 1
    # password IS preserved in raw_json (immutable provenance)
    assert "SHOULD_NOT_BE_STORED" in raw_rows[0][0]

    # Verify the full events row as a string doesn't contain the password
    full_row_str = str(events_rows[0])
    assert "SHOULD_NOT_BE_STORED" not in full_row_str


# ---------------------------------------------------------------------------
# Batch ingestion
# ---------------------------------------------------------------------------


def test_ingest_batch_of_five():
    events = [_cowrie_event() for _ in range(5)]
    receipt = _ingest(events)
    assert receipt["accepted"] == 5
    assert receipt["rejected"] == 0


def test_ingest_batch_partial_failure_missing_ts():
    """One event with a bad timestamp should reject only that event."""
    good = _cowrie_event()
    bad = _cowrie_event()
    bad["ts"] = "not-a-timestamp"
    receipt = _ingest([good, bad, _cowrie_event()])
    assert receipt["accepted"] == 2
    assert receipt["rejected"] == 1
    assert len(receipt["errors"]) == 1
    assert receipt["errors"][0]["index"] == 1


def test_ingest_oversized_batch_rejected():
    """501 events exceeds the max_length=500 constraint — FastAPI returns 422."""
    events = [_cowrie_event() for _ in range(501)]
    r = client.post("/api/ingest", json={"events": events}, headers=HEADERS)
    assert r.status_code == 422


def test_ingest_empty_batch_rejected():
    """min_length=1 constraint — FastAPI returns 422."""
    r = client.post("/api/ingest", json={"events": []}, headers=HEADERS)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_ingest_deduplication_same_id_twice():
    """Second POST with same event id must be counted as duplicate, not error."""
    event = _cowrie_event()
    r1 = _ingest([event])
    assert r1["accepted"] == 1

    r2 = _ingest([event])
    assert r2["accepted"] == 0
    assert r2["duplicate"] == 1
    assert r2["errors"] == []


def test_ingest_dedup_does_not_create_duplicate_db_rows():
    eid = str(uuid.uuid4())
    event = _cowrie_event(event_id=eid)
    _ingest([event])
    _ingest([event])
    rows = _db_query("SELECT id FROM raw_events WHERE id = :id", {"id": eid})
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_ingest_event_with_no_ip_accepted_with_null_src_ip():
    """Events without an extractable IP must be accepted with src_ip=NULL."""
    eid = str(uuid.uuid4())
    event = {
        "id": eid,
        "ts": "2025-10-28T18:31:08+00:00",
        "source": "cowrie",
        "type": "cowrie.login.failed",
        "data": {"username": "root", "password": "bad"},  # no ip field
    }
    receipt = _ingest([event])
    assert receipt["accepted"] == 1

    rows = _db_query("SELECT src_ip FROM events WHERE id = :id", {"id": eid})
    assert rows[0][0] is None


def test_ingest_private_ip_not_stored_in_src_ip():
    """Private IPs must not be extracted as src_ip."""
    eid = str(uuid.uuid4())
    _ingest([_cowrie_event(event_id=eid, ip="192.168.1.1")])
    rows = _db_query("SELECT src_ip FROM events WHERE id = :id", {"id": eid})
    assert rows[0][0] is None


def test_ingest_normalizes_cowrie_event_type():
    """cowrie.login.failed → auth_failed via normalize_event_type."""
    eid = str(uuid.uuid4())
    _ingest([_cowrie_event(event_id=eid, event_type="cowrie.login.failed")])
    rows = _db_query("SELECT event_type FROM events WHERE id = :id", {"id": eid})
    assert rows[0][0] == "auth_failed"


def test_ingest_unknown_event_type_coerced():
    """Unmapped sensor types are coerced to 'unknown' to prevent FK violations."""
    eid = str(uuid.uuid4())
    event = _cowrie_event(event_id=eid, event_type="cowrie.client.version")
    receipt = _ingest([event])
    assert receipt["accepted"] == 1
    rows = _db_query("SELECT event_type FROM events WHERE id = :id", {"id": eid})
    assert rows[0][0] == "unknown"
