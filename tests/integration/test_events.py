"""
Integration tests for GET /api/events.

Tests hit the full HTTP stack against the in-memory SQLite DB.
Schema is bootstrapped by tests/conftest.py; rows are reset per test by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

_EXPECTED_ITEM_KEYS = {
    "id",
    "ts",
    "src_ip",
    "dst_port",
    "protocol",
    "event_type",
    "service",
    "country_code",
    "country_name",
    "city",
    "asn",
    "asn_org",
    "campaign_id",
    "schema_version",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingest(events: list[dict]) -> None:
    r = client.post("/api/ingest", json={"events": events}, headers=HEADERS)
    assert r.status_code == 200, r.text


def _event(ts: str | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "ts": ts or datetime.now(UTC).isoformat(),
        "source": "cowrie",
        "type": "cowrie.login.failed",
        "data": {"ip": "1.2.3.4", "username": "root", "password": "bad"},
    }


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_events_requires_api_key():
    r = client.get("/api/events")
    assert r.status_code == 401


def test_events_wrong_key_rejected():
    r = client.get("/api/events", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Empty baseline
# ---------------------------------------------------------------------------


def test_events_empty_db_returns_empty_items():
    r = client.get("/api/events", headers={"x-api-key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["items"] == []


# ---------------------------------------------------------------------------
# Response contract
# ---------------------------------------------------------------------------


def test_events_response_has_items_key():
    _ingest([_event()])
    r = client.get("/api/events", headers={"x-api-key": API_KEY})
    assert r.status_code == 200
    assert "items" in r.json()


def test_events_item_has_expected_keys():
    _ingest([_event()])
    items = client.get("/api/events", headers={"x-api-key": API_KEY}).json()["items"]
    assert len(items) == 1
    assert set(items[0].keys()) == _EXPECTED_ITEM_KEYS


# ---------------------------------------------------------------------------
# Ordering — newest first
# ---------------------------------------------------------------------------


def test_events_returns_newest_first():
    now = datetime.now(UTC)
    old = now - timedelta(hours=2)
    older = now - timedelta(hours=4)

    e_old = _event(ts=old.isoformat())
    e_older = _event(ts=older.isoformat())
    e_now = _event(ts=now.isoformat())
    # Ingest in scrambled order to confirm DB ordering, not insertion order
    _ingest([e_old, e_older, e_now])

    items = client.get("/api/events", headers={"x-api-key": API_KEY}).json()["items"]
    assert len(items) == 3
    assert items[0]["id"] == e_now["id"]
    assert items[1]["id"] == e_old["id"]
    assert items[2]["id"] == e_older["id"]


# ---------------------------------------------------------------------------
# limit parameter
# ---------------------------------------------------------------------------


def test_events_limit_default_is_ten():
    for _ in range(15):
        _ingest([_event()])
    items = client.get("/api/events", headers={"x-api-key": API_KEY}).json()["items"]
    assert len(items) == 10


def test_events_limit_respected():
    for _ in range(5):
        _ingest([_event()])
    items = client.get("/api/events", headers={"x-api-key": API_KEY}, params={"limit": 2}).json()[
        "items"
    ]
    assert len(items) == 2


def test_events_limit_larger_than_total_returns_all():
    _ingest([_event(), _event()])
    items = client.get("/api/events", headers={"x-api-key": API_KEY}, params={"limit": 100}).json()[
        "items"
    ]
    assert len(items) == 2


# ---------------------------------------------------------------------------
# Field values
# ---------------------------------------------------------------------------


def test_events_event_type_is_normalized():
    _ingest([_event()])
    items = client.get("/api/events", headers={"x-api-key": API_KEY}).json()["items"]
    assert items[0]["event_type"] == "auth_failed"


def test_events_src_ip_is_extracted():
    _ingest([_event()])
    items = client.get("/api/events", headers={"x-api-key": API_KEY}).json()["items"]
    assert items[0]["src_ip"] == "1.2.3.4"
