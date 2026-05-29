"""Integration tests for Phase 7 Group A3 — sparse campaign surface API.

Tests hit the full stack: FastAPI TestClient → routers → EventRepository → in-memory SQLite.

Coverage:
  GET  /api/campaigns/sparse:
    - returns 200 with empty list when no sparse campaigns
    - returns sparse campaigns (no representative fingerprint)
    - campaigns with fingerprint are excluded
    - each sparse item has has_fingerprint, observation_count, density_score
    - respects limit parameter
    - requires authentication

  GET  /api/campaigns/{id}/density:
    - returns 200 for known campaign
    - returns 404 for unknown campaign
    - sparse campaign (no fingerprint) has classification="sparse", density_score=0.0
    - campaign with fingerprint has has_fingerprint=True and all metric fields
    - response includes thresholds block
    - requires authentication

  GET  /api/campaigns (existing list endpoint):
    - returns evidence_quality and density_score on each item
    - has_fingerprint flag is correct on each item
    - requires authentication

  Invariants:
    - campaigns router does not import from app.ai
    - sparse endpoint does not modify any campaign data
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.main import app

client = TestClient(app)

_API_KEY = "test-key"
_HEADERS = {"X-API-Key": _API_KEY}


@pytest.fixture(autouse=True)
def setup_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", _API_KEY)
    monkeypatch.setenv("FEED_SALT", "test-salt")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _create_campaign(
    *,
    status: str = "active",
    representative_fingerprint_json: str | None = None,
) -> str:
    cid = str(uuid.uuid4())
    now = _now()
    with get_session() as session:
        EventRepository(session).create_campaign(
            campaign_id=cid,
            name=f"test-{cid[:8]}",
            status=status,
            confidence=0.7,
            first_seen=now,
            last_seen=now,
            member_ip_count=1,
            created_at=now,
            updated_at=now,
        )
        if representative_fingerprint_json is not None:
            session.execute(
                text("UPDATE campaigns SET representative_fingerprint_json = :fp WHERE id = :id"),
                {"fp": representative_fingerprint_json, "id": cid},
            )
    return cid


def _add_observation(campaign_id: str, *, reviewed: bool = False) -> None:
    with get_session() as session:
        session.execute(
            text("""
                INSERT INTO campaign_observations
                    (id, campaign_id, source_ip, observed_at, event_count,
                     is_reactivation, dormancy_gap_days, notes, analyst_review_json)
                VALUES (:id, :cid, '10.0.0.1', :ts, 5, 0, NULL, NULL, :review)
            """),
            {
                "id": str(uuid.uuid4()),
                "cid": campaign_id,
                "ts": _now(),
                "review": '{"decision":"analyst_confirmed"}' if reviewed else None,
            },
        )


# ---------------------------------------------------------------------------
# GET /api/campaigns/sparse
# ---------------------------------------------------------------------------


def test_sparse_list_empty_when_all_have_fingerprint():
    _create_campaign(representative_fingerprint_json='{"x":1}')
    resp = client.get("/api/campaigns/sparse", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_sparse_list_returns_campaigns_without_fingerprint():
    cid_sparse = _create_campaign()
    cid_rich = _create_campaign(representative_fingerprint_json='{"x":1}')

    resp = client.get("/api/campaigns/sparse", headers=_HEADERS)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert cid_sparse in ids
    assert cid_rich not in ids


def test_sparse_list_items_have_required_fields():
    _create_campaign()
    resp = client.get("/api/campaigns/sparse", headers=_HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    item = items[0]
    assert "has_fingerprint" in item
    assert item["has_fingerprint"] is False
    assert "observation_count" in item
    assert "review_count" in item
    assert "age_span_hours" in item
    assert "density_score" in item
    assert "evidence_quality" in item
    assert item["evidence_quality"] == "sparse"
    assert item["density_score"] == 0.0


def test_sparse_list_respects_limit():
    for _ in range(5):
        _create_campaign()
    resp = client.get("/api/campaigns/sparse?limit=2", headers=_HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) <= 2


def test_sparse_list_requires_auth():
    resp = client.get("/api/campaigns/sparse")
    assert resp.status_code == 401


def test_sparse_list_includes_observation_counts():
    cid = _create_campaign()
    _add_observation(cid, reviewed=True)
    _add_observation(cid, reviewed=False)

    resp = client.get("/api/campaigns/sparse", headers=_HEADERS)
    assert resp.status_code == 200
    items = {i["id"]: i for i in resp.json()["items"]}
    assert cid in items
    assert items[cid]["observation_count"] == 2
    assert items[cid]["review_count"] == 1


def test_sparse_list_includes_sparse_criteria_field():
    resp = client.get("/api/campaigns/sparse", headers=_HEADERS)
    assert resp.status_code == 200
    assert "sparse_criteria" in resp.json()


# ---------------------------------------------------------------------------
# GET /api/campaigns/{id}/density
# ---------------------------------------------------------------------------


def test_density_endpoint_returns_404_for_unknown():
    resp = client.get(f"/api/campaigns/{uuid.uuid4()}/density", headers=_HEADERS)
    assert resp.status_code == 404


def test_density_endpoint_requires_auth():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/density")
    assert resp.status_code == 401


def test_density_endpoint_sparse_campaign():
    cid = _create_campaign(representative_fingerprint_json=None)

    resp = client.get(f"/api/campaigns/{cid}/density", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["campaign_id"] == cid
    assert data["has_fingerprint"] is False
    assert data["density_score"] == 0.0
    assert data["evidence_quality"] == "sparse"


def test_density_endpoint_campaign_with_fingerprint():
    cid = _create_campaign(representative_fingerprint_json='{"confidence": 0.8}')

    resp = client.get(f"/api/campaigns/{cid}/density", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_fingerprint"] is True
    assert data["evidence_quality"] in {"sparse", "emerging", "established", "mature"}
    assert "density_components" in data
    assert set(data["density_components"].keys()) == {
        "obs_score",
        "ip_score",
        "age_score",
        "review_score",
    }


def test_density_endpoint_includes_thresholds():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/density", headers=_HEADERS)
    assert resp.status_code == 200
    thresholds = resp.json()["thresholds"]
    assert "obs_mature" in thresholds
    assert "ip_mature" in thresholds
    assert "age_hours_mature" in thresholds
    assert "density_mature" in thresholds
    assert "density_established" in thresholds


def test_density_endpoint_includes_observation_counts():
    cid = _create_campaign()
    _add_observation(cid, reviewed=True)

    resp = client.get(f"/api/campaigns/{cid}/density", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["observation_count"] == 1
    assert data["review_count"] == 1


def test_density_endpoint_returns_campaign_name():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/density", headers=_HEADERS)
    assert resp.status_code == 200
    assert "campaign_name" in resp.json()


# ---------------------------------------------------------------------------
# GET /api/campaigns (list endpoint — evidence_quality annotation)
# ---------------------------------------------------------------------------


def test_campaign_list_includes_evidence_quality():
    _create_campaign()
    resp = client.get("/api/campaigns", headers=_HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    if items:
        assert "evidence_quality" in items[0]
        assert "density_score" in items[0]
        assert "has_fingerprint" in items[0]


def test_campaign_list_sparse_has_has_fingerprint_false():
    _create_campaign(representative_fingerprint_json=None)
    resp = client.get("/api/campaigns", headers=_HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    sparse_items = [i for i in items if not i.get("has_fingerprint", True)]
    for item in sparse_items:
        assert item["evidence_quality"] == "sparse"
        assert item["density_score"] == 0.0


def test_campaign_list_with_fingerprint_has_has_fingerprint_true():
    _create_campaign(representative_fingerprint_json='{"x":1}')
    resp = client.get("/api/campaigns", headers=_HEADERS)
    assert resp.status_code == 200
    items = resp.json()["items"]
    fp_items = [i for i in items if i.get("has_fingerprint")]
    for item in fp_items:
        assert item["evidence_quality"] in {"emerging", "established", "mature"}


def test_campaign_list_requires_auth():
    resp = client.get("/api/campaigns")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_campaigns_router_does_not_import_ai():
    import importlib

    mod = importlib.import_module("app.routers.campaigns")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content


def test_sparse_endpoint_does_not_modify_campaigns():
    cid = _create_campaign()
    with get_session() as session:
        before = EventRepository(session).get_campaign(cid)

    client.get("/api/campaigns/sparse", headers=_HEADERS)

    with get_session() as session:
        after = EventRepository(session).get_campaign(cid)

    assert before["updated_at"] == after["updated_at"]
    assert before["status"] == after["status"]
