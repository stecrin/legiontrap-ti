"""Integration tests for POST /api/admin/run-lifecycle-job.

Tests hit the full HTTP → router → repository → SQLite stack.
Schema is bootstrapped by tests/conftest.py; rows reset per test by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.intelligence.constants import CAMPAIGN_ACTIVE_DAYS, CAMPAIGN_DORMANT_DAYS
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY}

_BASE_TS = "2025-01-01T00:00:00+00:00"

# Timestamps anchored to real time so the lifecycle job (which uses datetime.now)
# sees them as definitively old vs. recent.
_NOW = datetime.now(UTC)
_OLD_LAST_SEEN = (_NOW - timedelta(days=CAMPAIGN_ACTIVE_DAYS + 10)).isoformat()
_RECENT_LAST_SEEN = (_NOW - timedelta(days=1)).isoformat()
_OLD_DORMANT_SINCE = (_NOW - timedelta(days=CAMPAIGN_DORMANT_DAYS + 10)).isoformat()
_RECENT_DORMANT_SINCE = (_NOW - timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_campaign(
    status: str = "active",
    last_seen: str = _OLD_LAST_SEEN,
    dormant_since: str | None = None,
) -> str:
    cid = str(uuid.uuid4())
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaigns
                    (id, name, status, confidence, first_seen, last_seen,
                     dormant_since, reactivation_count, member_ip_count,
                     attack_tactic_dist, top_target_ports, notes,
                     created_at, updated_at)
                VALUES
                    (:id, :name, :status, 0.7, :base_ts, :last_seen,
                     :dormant_since, 0, 0, NULL, NULL, NULL,
                     :base_ts, :base_ts)
            """),
            {
                "id": cid,
                "name": f"TEST-{cid[:8]}",
                "status": status,
                "base_ts": _BASE_TS,
                "last_seen": last_seen,
                "dormant_since": dormant_since,
            },
        )
        conn.commit()
    return cid


def _get_status(cid: str) -> str:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status FROM campaigns WHERE id = :id"), {"id": cid}
        ).fetchone()
    return row[0]


def _get_dormant_since(cid: str) -> str | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT dormant_since FROM campaigns WHERE id = :id"), {"id": cid}
        ).fetchone()
    return row[0]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_lifecycle_endpoint_requires_api_key():
    r = client.post("/api/admin/run-lifecycle-job")
    assert r.status_code == 401


def test_lifecycle_endpoint_rejects_wrong_api_key():
    r = client.post("/api/admin/run-lifecycle-job", headers={"x-api-key": "wrong-key"})
    assert r.status_code == 401


def test_lifecycle_endpoint_rejects_jwt_only():
    """The admin endpoint must not accept a JWT — API key only."""
    import os

    from jose import jwt as jose_jwt

    secret = os.getenv("JWT_SECRET", "test-secret")
    token = jose_jwt.encode({"sub": "admin"}, secret, algorithm="HS256")
    r = client.post(
        "/api/admin/run-lifecycle-job",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_lifecycle_endpoint_returns_200_with_valid_key():
    r = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    assert r.status_code == 200


def test_lifecycle_endpoint_response_has_required_keys():
    r = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    body = r.json()
    assert "active_to_dormant" in body
    assert "dormant_to_historical" in body
    assert "evaluated_at" in body


def test_lifecycle_endpoint_counts_are_integers():
    r = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    body = r.json()
    assert isinstance(body["active_to_dormant"], int)
    assert isinstance(body["dormant_to_historical"], int)


def test_lifecycle_endpoint_returns_zero_when_no_campaigns():
    r = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    body = r.json()
    assert body["active_to_dormant"] == 0
    assert body["dormant_to_historical"] == 0


# ---------------------------------------------------------------------------
# Functional: DB state is updated
# ---------------------------------------------------------------------------


def test_lifecycle_endpoint_transitions_active_to_dormant():
    cid = _insert_campaign(status="active", last_seen=_OLD_LAST_SEEN)
    r = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["active_to_dormant"] >= 1
    assert _get_status(cid) == "dormant"


def test_lifecycle_endpoint_sets_dormant_since_on_transition():
    cid = _insert_campaign(status="active", last_seen=_OLD_LAST_SEEN)
    client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    assert _get_dormant_since(cid) is not None


def test_lifecycle_endpoint_transitions_dormant_to_historical():
    cid = _insert_campaign(
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_OLD_DORMANT_SINCE,
    )
    r = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["dormant_to_historical"] >= 1
    assert _get_status(cid) == "historical"


def test_lifecycle_endpoint_leaves_recent_active_untouched():
    cid = _insert_campaign(status="active", last_seen=_RECENT_LAST_SEEN)
    client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    assert _get_status(cid) == "active"


def test_lifecycle_endpoint_leaves_recent_dormant_untouched():
    cid = _insert_campaign(
        status="dormant",
        last_seen=_OLD_LAST_SEEN,
        dormant_since=_RECENT_DORMANT_SINCE,
    )
    client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    assert _get_status(cid) == "dormant"


def test_lifecycle_endpoint_idempotent():
    """Calling the endpoint twice produces the same final state."""
    cid = _insert_campaign(status="active", last_seen=_OLD_LAST_SEEN)
    r1 = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    r2 = client.post("/api/admin/run-lifecycle-job", headers=HEADERS)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["active_to_dormant"] == 0
    assert _get_status(cid) == "dormant"
