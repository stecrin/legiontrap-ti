"""
Integration tests for GET /api/intelligence/ips and GET /api/intelligence/ips/{ip}.

Tests hit the full HTTP → router → repository → in-memory SQLite stack.
Schema is bootstrapped by tests/conftest.py; rows are reset per test by
tests/integration/conftest.py (reset_db_rows fixture).

All tests insert source_ips rows directly for deterministic control over
reputation_score, event_count, and tags without depending on GeoIP MMDB.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY}

_REQUIRED_FIELDS = {
    "ip",
    "first_seen",
    "last_seen",
    "event_count",
    "country_code",
    "country_name",
    "city",
    "asn",
    "asn_org",
    "tags",
    "reputation_score",
}

# Single-IP profile includes event_type_breakdown; list endpoint does not.
_PROFILE_FIELDS = _REQUIRED_FIELDS | {"event_type_breakdown"}

_TS = "2025-10-28T18:31:08+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_source_ip(
    ip: str,
    event_count: int = 1,
    reputation_score: float | None = None,
    tags: list[str] | None = None,
    country_code: str | None = None,
    country_name: str | None = None,
) -> None:
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO source_ips
                    (ip, first_seen, last_seen, event_count,
                     reputation_score, tags, country_code, country_name)
                VALUES
                    (:ip, :ts, :ts, :ec, :score, :tags, :cc, :cn)
                """),
            {
                "ip": ip,
                "ts": _TS,
                "ec": event_count,
                "score": reputation_score,
                "tags": json.dumps(tags) if tags is not None else None,
                "cc": country_code,
                "cn": country_name,
            },
        )
        conn.commit()


def _insert_event(
    ip: str,
    event_type: str = "auth_failed",
    event_id: str | None = None,
) -> None:
    """Insert a raw_events + events row pair for testing event_type_breakdown."""
    import uuid as _uuid

    eid = event_id or str(_uuid.uuid4())
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO raw_events (id, ts, ingested_at, source, raw_json)
                VALUES (:id, :ts, :ts, 'test', '{}')
                """),
            {"id": eid, "ts": _TS},
        )
        conn.execute(
            text("""
                INSERT OR IGNORE INTO events
                    (id, ts, src_ip, event_type, schema_version)
                VALUES (:id, :ts, :ip, :et, 1)
                """),
            {"id": eid, "ts": _TS, "ip": ip, "et": event_type},
        )
        conn.commit()


# ---------------------------------------------------------------------------
# GET /api/intelligence/ips — list
# ---------------------------------------------------------------------------


def test_list_ips_empty_db():
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_list_ips_returns_required_fields():
    _insert_source_ip("1.2.3.4")
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert _REQUIRED_FIELDS.issubset(item.keys())


def test_list_ips_city_is_null():
    """city is not stored in source_ips — must be present but null."""
    _insert_source_ip("1.2.3.4")
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    item = resp.json()["items"][0]
    assert "city" in item
    assert item["city"] is None


def test_list_ips_tags_returned_as_list():
    _insert_source_ip("1.2.3.4", tags=["brute-force", "scanner"])
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    item = resp.json()["items"][0]
    assert isinstance(item["tags"], list)
    assert "brute-force" in item["tags"]
    assert "scanner" in item["tags"]


def test_list_ips_null_tags_returned_as_empty_list():
    _insert_source_ip("1.2.3.4", tags=None)
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    item = resp.json()["items"][0]
    assert item["tags"] == []


def test_list_ips_sorted_by_reputation_score_desc():
    _insert_source_ip("10.0.0.1", reputation_score=0.2)
    _insert_source_ip("10.0.0.2", reputation_score=0.9)
    _insert_source_ip("10.0.0.3", reputation_score=0.5)
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    scores = [item["reputation_score"] for item in resp.json()["items"]]
    assert scores == sorted(scores, reverse=True)


def test_list_ips_sorted_by_event_count_when_scores_equal():
    """When reputation_score is tied (or both NULL), higher event_count ranks first."""
    _insert_source_ip("20.0.0.1", event_count=10, reputation_score=0.3)
    _insert_source_ip("20.0.0.2", event_count=50, reputation_score=0.3)
    _insert_source_ip("20.0.0.3", event_count=1, reputation_score=0.3)
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    items = resp.json()["items"]
    counts = [i["event_count"] for i in items]
    assert counts == sorted(counts, reverse=True)


def test_list_ips_null_score_sorts_last():
    _insert_source_ip("30.0.0.1", reputation_score=0.5)
    _insert_source_ip("30.0.0.2", reputation_score=None)
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    items = resp.json()["items"]
    scored = [i for i in items if i["reputation_score"] is not None]
    unscored = [i for i in items if i["reputation_score"] is None]
    # All scored IPs must appear before unscored ones
    assert items.index(scored[-1]) < items.index(unscored[0])


def test_list_ips_limit_respected():
    for i in range(5):
        _insert_source_ip(f"40.0.0.{i + 1}")
    resp = client.get("/api/intelligence/ips?limit=3", headers=HEADERS)
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["count"] == 3


def test_list_ips_limit_default_is_100():
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    assert resp.status_code == 200  # default limit accepted


def test_list_ips_limit_below_minimum_returns_422():
    resp = client.get("/api/intelligence/ips?limit=0", headers=HEADERS)
    assert resp.status_code == 422


def test_list_ips_limit_above_maximum_returns_422():
    resp = client.get("/api/intelligence/ips?limit=1001", headers=HEADERS)
    assert resp.status_code == 422


def test_list_ips_count_matches_items_length():
    _insert_source_ip("50.0.0.1")
    _insert_source_ip("50.0.0.2")
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    data = resp.json()
    assert data["count"] == len(data["items"])


# ---------------------------------------------------------------------------
# GET /api/intelligence/ips/{ip} — single IP profile
# ---------------------------------------------------------------------------


def test_get_ip_returns_profile():
    _insert_source_ip("60.0.0.1", event_count=42, reputation_score=0.7, tags=["brute-force"])
    resp = client.get("/api/intelligence/ips/60.0.0.1", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ip"] == "60.0.0.1"
    assert data["event_count"] == 42
    assert data["reputation_score"] == pytest.approx(0.7)
    assert "brute-force" in data["tags"]


def test_get_ip_returns_all_required_fields():
    _insert_source_ip("60.0.0.2")
    resp = client.get("/api/intelligence/ips/60.0.0.2", headers=HEADERS)
    assert resp.status_code == 200
    assert _PROFILE_FIELDS.issubset(resp.json().keys())


def test_get_ip_404_for_unknown():
    resp = client.get("/api/intelligence/ips/99.99.99.99", headers=HEADERS)
    assert resp.status_code == 404


def test_get_ip_city_is_null():
    _insert_source_ip("60.0.0.3", country_code="US")
    resp = client.get("/api/intelligence/ips/60.0.0.3", headers=HEADERS)
    assert resp.json()["city"] is None


def test_get_ip_country_fields_populated():
    _insert_source_ip("60.0.0.4", country_code="DE", country_name="Germany")
    resp = client.get("/api/intelligence/ips/60.0.0.4", headers=HEADERS)
    data = resp.json()
    assert data["country_code"] == "DE"
    assert data["country_name"] == "Germany"


# ---------------------------------------------------------------------------
# Auth tests — both endpoints must reject missing/wrong credentials
# ---------------------------------------------------------------------------


def test_list_ips_no_auth_returns_401():
    resp = client.get("/api/intelligence/ips")
    assert resp.status_code == 401


def test_list_ips_wrong_api_key_returns_401():
    resp = client.get("/api/intelligence/ips", headers={"x-api-key": "wrong-key"})
    assert resp.status_code == 401


def test_get_ip_no_auth_returns_401():
    resp = client.get("/api/intelligence/ips/1.2.3.4")
    assert resp.status_code == 401


def test_get_ip_wrong_api_key_returns_401():
    resp = client.get("/api/intelligence/ips/1.2.3.4", headers={"x-api-key": "bad"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# event_type_breakdown — single-IP profile contract (Phase 3 PR 1)
# ---------------------------------------------------------------------------


def test_get_ip_breakdown_present_in_profile():
    """event_type_breakdown must be present in single-IP response."""
    _insert_source_ip("70.0.0.1")
    resp = client.get("/api/intelligence/ips/70.0.0.1", headers=HEADERS)
    assert resp.status_code == 200
    assert "event_type_breakdown" in resp.json()


def test_get_ip_breakdown_empty_when_no_events():
    """breakdown is an empty dict when source_ips exists but events table has no rows."""
    _insert_source_ip("70.0.0.2")
    resp = client.get("/api/intelligence/ips/70.0.0.2", headers=HEADERS)
    assert resp.json()["event_type_breakdown"] == {}


def test_get_ip_breakdown_counts_single_type():
    """Three auth_failed events → breakdown shows auth_failed: 3."""
    _insert_source_ip("70.0.0.3", event_count=3)
    _insert_event("70.0.0.3", "auth_failed")
    _insert_event("70.0.0.3", "auth_failed")
    _insert_event("70.0.0.3", "auth_failed")
    resp = client.get("/api/intelligence/ips/70.0.0.3", headers=HEADERS)
    breakdown = resp.json()["event_type_breakdown"]
    assert breakdown["auth_failed"] == 3
    assert len(breakdown) == 1


def test_get_ip_breakdown_counts_multiple_types():
    """Mixed event types — each type counted independently."""
    _insert_source_ip("70.0.0.4", event_count=3)
    _insert_event("70.0.0.4", "auth_failed")
    _insert_event("70.0.0.4", "auth_failed")
    _insert_event("70.0.0.4", "port_scan")
    resp = client.get("/api/intelligence/ips/70.0.0.4", headers=HEADERS)
    breakdown = resp.json()["event_type_breakdown"]
    assert breakdown["auth_failed"] == 2
    assert breakdown["port_scan"] == 1
    assert len(breakdown) == 2


def test_get_ip_breakdown_is_dict():
    """event_type_breakdown must be a JSON object, not a list or string."""
    _insert_source_ip("70.0.0.5")
    _insert_event("70.0.0.5", "command_exec")
    resp = client.get("/api/intelligence/ips/70.0.0.5", headers=HEADERS)
    assert isinstance(resp.json()["event_type_breakdown"], dict)


def test_list_ips_does_not_include_breakdown():
    """List endpoint must NOT include event_type_breakdown — it's profile-only."""
    _insert_source_ip("70.0.0.6")
    resp = client.get("/api/intelligence/ips", headers=HEADERS)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert "event_type_breakdown" not in item


def test_get_ip_breakdown_only_counts_own_ip():
    """Breakdown must count only events from the queried IP, not other IPs."""
    _insert_source_ip("70.0.0.7")
    _insert_source_ip("70.0.0.8")
    _insert_event("70.0.0.7", "auth_failed")
    _insert_event("70.0.0.8", "port_scan")
    resp = client.get("/api/intelligence/ips/70.0.0.7", headers=HEADERS)
    breakdown = resp.json()["event_type_breakdown"]
    assert breakdown == {"auth_failed": 1}
    assert "port_scan" not in breakdown
