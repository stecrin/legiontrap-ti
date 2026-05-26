"""Integration tests for the campaign API endpoints.

Tests hit the full HTTP → router → repository → in-memory SQLite stack.
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

_TS = "2025-06-01T12:00:00+00:00"
_IP = "10.0.0.1"
_IP2 = "10.0.0.2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_source_ip(ip: str = _IP) -> None:
    with get_engine().connect() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO source_ips"
                " (ip, first_seen, last_seen, event_count) VALUES (:ip, :ts, :ts, 1)"
            ),
            {"ip": ip, "ts": _TS},
        )
        conn.commit()


def _insert_campaign(
    campaign_id: str | None = None,
    status: str = "active",
    last_seen: str = _TS,
    name: str = "TEST-WOLF-1",
) -> str:
    cid = campaign_id or str(uuid.uuid4())
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaigns
                    (id, name, status, confidence, first_seen, last_seen,
                     dormant_since, reactivation_count, member_ip_count,
                     attack_tactic_dist, top_target_ports, notes,
                     created_at, updated_at)
                VALUES
                    (:id, :name, :status, 0.7, :ts, :last_seen,
                     NULL, 0, 1,
                     NULL, NULL, NULL,
                     :ts, :ts)
            """),
            {"id": cid, "name": name, "status": status, "ts": _TS, "last_seen": last_seen},
        )
        conn.commit()
    return cid


def _insert_member(campaign_id: str, ip: str = _IP) -> None:
    _insert_source_ip(ip)
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:cid, :ip, 0.8, :ts, :ts)
            """),
            {"cid": campaign_id, "ip": ip, "ts": _TS},
        )
        conn.commit()


def _insert_observation(
    campaign_id: str,
    ip: str = _IP,
    is_reactivation: bool = False,
    notes: str | None = None,
    observed_at: str = _TS,
) -> None:
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO campaign_observations
                    (id, campaign_id, source_ip, observed_at, event_count,
                     is_reactivation, dormancy_gap_days, notes)
                VALUES (:id, :cid, :ip, :ts, 10, :is_react, NULL, :notes)
            """),
            {
                "id": str(uuid.uuid4()),
                "cid": campaign_id,
                "ip": ip,
                "ts": observed_at,
                "is_react": 1 if is_reactivation else 0,
                "notes": notes,
            },
        )
        conn.commit()


# ---------------------------------------------------------------------------
# GET /api/campaigns — list
# ---------------------------------------------------------------------------


def test_list_campaigns_empty_returns_empty():
    resp = client.get("/api/campaigns", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_list_campaigns_returns_inserted_campaign():
    cid = _insert_campaign()
    resp = client.get("/api/campaigns", headers=HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == cid


def test_list_campaigns_count_matches_items():
    _insert_campaign()
    _insert_campaign()
    resp = client.get("/api/campaigns", headers=HEADERS)
    data = resp.json()
    assert data["count"] == len(data["items"])


def test_list_campaigns_required_fields():
    _insert_campaign()
    resp = client.get("/api/campaigns", headers=HEADERS)
    item = resp.json()["items"][0]
    required = {
        "id",
        "name",
        "status",
        "confidence",
        "first_seen",
        "last_seen",
        "dormant_since",
        "reactivation_count",
        "member_ip_count",
        "attack_tactic_dist",
        "top_target_ports",
        "notes",
        "created_at",
        "updated_at",
    }
    assert required.issubset(item.keys())


def test_list_campaigns_sorted_by_last_seen_desc():
    _insert_campaign(last_seen="2025-06-01T00:00:00+00:00")
    _insert_campaign(last_seen="2025-08-01T00:00:00+00:00")
    _insert_campaign(last_seen="2025-07-01T00:00:00+00:00")
    resp = client.get("/api/campaigns", headers=HEADERS)
    dates = [item["last_seen"] for item in resp.json()["items"]]
    assert dates == sorted(dates, reverse=True)


def test_list_campaigns_limit_respected():
    for i in range(5):
        _insert_campaign(name=f"WOLF-{i}")
    resp = client.get("/api/campaigns?limit=3", headers=HEADERS)
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["count"] == 3


def test_list_campaigns_limit_below_minimum_returns_422():
    resp = client.get("/api/campaigns?limit=0", headers=HEADERS)
    assert resp.status_code == 422


def test_list_campaigns_limit_above_maximum_returns_422():
    resp = client.get("/api/campaigns?limit=1001", headers=HEADERS)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/campaigns — auth
# ---------------------------------------------------------------------------


def test_list_campaigns_no_auth_returns_401():
    resp = client.get("/api/campaigns")
    assert resp.status_code == 401


def test_list_campaigns_wrong_key_returns_401():
    resp = client.get("/api/campaigns", headers={"x-api-key": "bad"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/campaigns/{campaign_id} — detail
# ---------------------------------------------------------------------------


def test_get_campaign_returns_detail():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == cid
    assert data["name"] == "TEST-WOLF-1"


def test_get_campaign_includes_members_key():
    cid = _insert_campaign()
    _insert_member(cid)
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "members" in data
    assert isinstance(data["members"], list)
    assert len(data["members"]) == 1
    assert data["members"][0]["source_ip"] == _IP


def test_get_campaign_includes_observations_key():
    cid = _insert_campaign()
    _insert_member(cid)
    _insert_observation(cid)
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "observations" in data
    assert len(data["observations"]) == 1


def test_get_campaign_members_empty_when_none():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    assert resp.json()["members"] == []


def test_get_campaign_observations_empty_when_none():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    assert resp.json()["observations"] == []


def test_get_campaign_observation_has_notes():
    cid = _insert_campaign()
    _insert_member(cid)
    notes = json.dumps({"weighted_total": 0.92, "decision": "automatic_association"})
    _insert_observation(cid, notes=notes)
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    obs = resp.json()["observations"][0]
    assert obs["notes"] == notes


def test_get_campaign_observation_is_reactivation_flag():
    cid = _insert_campaign()
    _insert_member(cid)
    _insert_observation(cid, is_reactivation=True)
    resp = client.get(f"/api/campaigns/{cid}", headers=HEADERS)
    obs = resp.json()["observations"][0]
    assert obs["is_reactivation"] is True


def test_get_campaign_not_found_returns_404():
    resp = client.get(f"/api/campaigns/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404


def test_get_campaign_no_auth_returns_401():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}")
    assert resp.status_code == 401


def test_get_campaign_wrong_key_returns_401():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}", headers={"x-api-key": "bad"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/campaigns/{campaign_id}/observations
# ---------------------------------------------------------------------------


def test_get_observations_empty_when_none():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}/observations", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_get_observations_returns_inserted():
    cid = _insert_campaign()
    _insert_member(cid)
    _insert_observation(cid)
    resp = client.get(f"/api/campaigns/{cid}/observations", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["items"][0]["campaign_id"] == cid


def test_get_observations_required_fields():
    cid = _insert_campaign()
    _insert_member(cid)
    _insert_observation(cid)
    resp = client.get(f"/api/campaigns/{cid}/observations", headers=HEADERS)
    obs = resp.json()["items"][0]
    required = {
        "id",
        "campaign_id",
        "source_ip",
        "observed_at",
        "event_count",
        "is_reactivation",
        "dormancy_gap_days",
        "notes",
    }
    assert required.issubset(obs.keys())


def test_get_observations_ordered_by_observed_at():
    cid = _insert_campaign()
    _insert_member(cid)
    _insert_observation(cid, observed_at="2025-06-03T00:00:00+00:00")
    _insert_observation(cid, observed_at="2025-06-01T00:00:00+00:00")
    _insert_observation(cid, observed_at="2025-06-02T00:00:00+00:00")
    resp = client.get(f"/api/campaigns/{cid}/observations", headers=HEADERS)
    items = resp.json()["items"]
    ts_list = [o["observed_at"] for o in items]
    assert ts_list == sorted(ts_list)


def test_get_observations_not_found_returns_404():
    resp = client.get(f"/api/campaigns/{uuid.uuid4()}/observations", headers=HEADERS)
    assert resp.status_code == 404


def test_get_observations_no_auth_returns_401():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}/observations")
    assert resp.status_code == 401


def test_get_observations_wrong_key_returns_401():
    cid = _insert_campaign()
    resp = client.get(f"/api/campaigns/{cid}/observations", headers={"x-api-key": "bad"})
    assert resp.status_code == 401
