"""Integration tests for POST /api/admin/run-analytics-job.

Tests hit the full HTTP → router → repository → SQLite stack.
Schema is bootstrapped by tests/conftest.py; rows reset per test by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY}

_BASE_TS = "2025-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_campaign(status: str = "active") -> str:
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
                    (:id, :name, :status, 0.7, :ts, :ts,
                     NULL, 0, 0, NULL, NULL, NULL, :ts, :ts)
            """),
            {"id": cid, "name": f"TEST-{cid[:8]}", "status": status, "ts": _BASE_TS},
        )
        conn.commit()
    return cid


def _insert_source_ip(ip: str) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO source_ips (ip, first_seen, last_seen, event_count)
                VALUES (:ip, :ts, :ts, 0)
            """),
            {"ip": ip, "ts": _BASE_TS},
        )
        conn.commit()


def _add_member(campaign_id: str, ip: str) -> None:
    _insert_source_ip(ip)
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:cid, :ip, 0.8, :ts, :ts)
            """),
            {"cid": campaign_id, "ip": ip, "ts": _BASE_TS},
        )
        conn.commit()


def _insert_event(
    eid: str, src_ip: str, event_type: str = "auth_failed", dst_port: int = 22
) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO raw_events (id, ts, ingested_at, source, raw_json)
                VALUES (:id, :ts, :ts, :ip, '{}')
            """),
            {"id": eid, "ts": _BASE_TS, "ip": src_ip},
        )
        conn.execute(
            text("""
                INSERT INTO events
                    (id, ts, src_ip, dst_port, protocol, event_type, schema_version)
                VALUES (:id, :ts, :src_ip, :dst_port, 'tcp', :event_type, 1)
            """),
            {
                "id": eid,
                "ts": _BASE_TS,
                "src_ip": src_ip,
                "dst_port": dst_port,
                "event_type": event_type,
            },
        )
        conn.commit()


def _get_analytics(cid: str) -> tuple[str | None, str | None]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT attack_tactic_dist, top_target_ports FROM campaigns WHERE id = :id"),
            {"id": cid},
        ).fetchone()
    return row[0], row[1]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_analytics_endpoint_requires_api_key():
    r = client.post("/api/admin/run-analytics-job")
    assert r.status_code == 401


def test_analytics_endpoint_rejects_wrong_api_key():
    r = client.post("/api/admin/run-analytics-job", headers={"x-api-key": "wrong-key"})
    assert r.status_code == 401


def test_analytics_endpoint_rejects_jwt_only():
    """The admin endpoint must not accept a JWT."""
    import os

    from jose import jwt as jose_jwt

    secret = os.getenv("JWT_SECRET", "test-secret")
    token = jose_jwt.encode({"sub": "admin"}, secret, algorithm="HS256")
    r = client.post(
        "/api/admin/run-analytics-job",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_analytics_endpoint_returns_200():
    r = client.post("/api/admin/run-analytics-job", headers=HEADERS)
    assert r.status_code == 200


def test_analytics_endpoint_response_has_required_keys():
    r = client.post("/api/admin/run-analytics-job", headers=HEADERS)
    body = r.json()
    assert "campaigns_updated" in body
    assert "refreshed_at" in body


def test_analytics_endpoint_count_is_integer():
    r = client.post("/api/admin/run-analytics-job", headers=HEADERS)
    assert isinstance(r.json()["campaigns_updated"], int)


def test_analytics_endpoint_zero_when_no_campaigns():
    r = client.post("/api/admin/run-analytics-job", headers=HEADERS)
    assert r.json()["campaigns_updated"] == 0


# ---------------------------------------------------------------------------
# Functional: DB state is updated
# ---------------------------------------------------------------------------


def test_analytics_endpoint_populates_attack_tactic_dist():
    cid = _insert_campaign()
    _add_member(cid, "192.168.1.1")
    _insert_event(str(uuid.uuid4()), "192.168.1.1", event_type="auth_failed", dst_port=22)
    _insert_event(str(uuid.uuid4()), "192.168.1.1", event_type="auth_failed", dst_port=22)

    r = client.post("/api/admin/run-analytics-job", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["campaigns_updated"] >= 1

    tactic_dist, _ = _get_analytics(cid)
    assert tactic_dist is not None
    dist = json.loads(tactic_dist)
    assert dist.get("Credential Access") == 2


def test_analytics_endpoint_populates_top_target_ports():
    cid = _insert_campaign()
    _add_member(cid, "192.168.1.2")
    for _ in range(3):
        _insert_event(str(uuid.uuid4()), "192.168.1.2", dst_port=22)
    _insert_event(str(uuid.uuid4()), "192.168.1.2", dst_port=80)

    client.post("/api/admin/run-analytics-job", headers=HEADERS)

    _, top_ports = _get_analytics(cid)
    assert top_ports is not None
    ports = json.loads(top_ports)
    assert ports[0]["port"] == 22
    assert ports[0]["count"] == 3


def test_analytics_endpoint_empty_campaign_leaves_null(db_session=None):
    cid = _insert_campaign()
    client.post("/api/admin/run-analytics-job", headers=HEADERS)
    tactic_dist, top_ports = _get_analytics(cid)
    assert tactic_dist is None
    assert top_ports is None


def test_analytics_endpoint_idempotent():
    cid = _insert_campaign()
    _add_member(cid, "192.168.1.3")
    _insert_event(str(uuid.uuid4()), "192.168.1.3", event_type="port_scan", dst_port=443)

    r1 = client.post("/api/admin/run-analytics-job", headers=HEADERS)
    r2 = client.post("/api/admin/run-analytics-job", headers=HEADERS)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["campaigns_updated"] == r2.json()["campaigns_updated"]

    tactic_dist, top_ports = _get_analytics(cid)
    assert json.loads(tactic_dist) == {"Discovery": 1}
    assert json.loads(top_ports) == [{"port": 443, "count": 1}]


def test_analytics_endpoint_updates_count_matches_campaign_count():
    _insert_campaign()
    _insert_campaign(status="dormant")
    _insert_campaign(status="historical")

    r = client.post("/api/admin/run-analytics-job", headers=HEADERS)
    assert r.json()["campaigns_updated"] == 3
