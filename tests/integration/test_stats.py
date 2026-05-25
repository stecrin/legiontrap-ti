"""
Integration tests for GET /api/stats.

Tests hit the full HTTP stack against the in-memory SQLite DB.
Schema is bootstrapped by tests/conftest.py; rows are reset per test by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ingest(events: list[dict]) -> None:
    r = client.post("/api/ingest", json={"events": events}, headers=HEADERS)
    assert r.status_code == 200, r.text


def _event(ip: str = "1.2.3.4", ts: str | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "ts": ts or datetime.now(UTC).isoformat(),
        "source": "cowrie",
        "type": "cowrie.login.failed",
        "data": {"ip": ip, "username": "root", "password": "bad"},
    }


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_stats_requires_api_key():
    r = client.get("/api/stats")
    assert r.status_code == 401


def test_stats_wrong_key_rejected():
    r = client.get("/api/stats", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Empty baseline
# ---------------------------------------------------------------------------


def test_stats_empty_db_returns_zeros():
    r = client.get("/api/stats", headers={"x-api-key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["total_events"] == 0
    assert body["unique_ips"] == 0
    assert body["last_24h"] == 0


def test_stats_response_contract_has_counts_dict():
    """Existing test_stats_with_key checks counts.total — must remain present."""
    r = client.get("/api/stats", headers={"x-api-key": API_KEY})
    body = r.json()
    assert "counts" in body
    assert "total" in body["counts"]
    assert body["counts"]["total"] == body["total_events"]


# ---------------------------------------------------------------------------
# Counts after ingest
# ---------------------------------------------------------------------------


def test_stats_total_events_increments():
    _ingest([_event("1.2.3.4"), _event("5.6.7.8")])
    body = client.get("/api/stats", headers={"x-api-key": API_KEY}).json()
    assert body["total_events"] == 2


def test_stats_unique_ips_deduplicates():
    # Two events from the same IP — unique_ips must be 1, not 2.
    _ingest([_event("1.2.3.4"), _event("1.2.3.4")])
    body = client.get("/api/stats", headers={"x-api-key": API_KEY}).json()
    assert body["total_events"] == 2
    assert body["unique_ips"] == 1


def test_stats_unique_ips_counts_distinct_sources():
    _ingest([_event("1.2.3.4"), _event("5.6.7.8"), _event("9.10.11.12")])
    body = client.get("/api/stats", headers={"x-api-key": API_KEY}).json()
    assert body["unique_ips"] == 3


def test_stats_unique_ips_ignores_null_src_ip():
    """Events without a public IP contribute to total_events but not unique_ips."""
    _ingest(
        [
            _event("1.2.3.4"),
            # no ip field → src_ip=NULL
            {
                "id": str(uuid.uuid4()),
                "ts": datetime.now(UTC).isoformat(),
                "source": "cowrie",
                "type": "cowrie.login.failed",
                "data": {"username": "root", "password": "bad"},
            },
        ]
    )
    body = client.get("/api/stats", headers={"x-api-key": API_KEY}).json()
    assert body["total_events"] == 2
    assert body["unique_ips"] == 1


# ---------------------------------------------------------------------------
# last_24h window
# ---------------------------------------------------------------------------


def test_stats_last_24h_includes_recent_events():
    _ingest([_event(ts=datetime.now(UTC).isoformat())])
    body = client.get("/api/stats", headers={"x-api-key": API_KEY}).json()
    assert body["last_24h"] == 1


def test_stats_last_24h_excludes_old_events():
    old_ts = "2020-01-01T00:00:00+00:00"
    _ingest(
        [
            _event(ip="1.2.3.4", ts=datetime.now(UTC).isoformat()),
            _event(ip="5.6.7.8", ts=old_ts),
        ]
    )
    body = client.get("/api/stats", headers={"x-api-key": API_KEY}).json()
    assert body["total_events"] == 2
    assert body["last_24h"] == 1
