"""Integration tests for Phase 7 Group B2 — campaign-actor linking API.

Tests hit the full stack: FastAPI TestClient → routers → EventRepository → SQLite.

Coverage:
  POST /api/actors/{id}/campaigns:
    - creates lineage, returns 201 with lineage dict
    - 404 if actor not found
    - 404 if campaign not found
    - 422 if relationship_type is invalid
    - 422 if confidence is out of range
    - 409 if the same actor/campaign pair is already linked
    - requires authentication

  GET /api/actors/{id}/campaigns:
    - returns empty list when actor has no links
    - returns linked campaigns with metadata
    - 404 if actor not found
    - requires authentication

  DELETE /api/actors/{id}/campaigns/{lineage_id}:
    - removes the lineage record, returns 204
    - 404 if lineage_id does not exist
    - 404 if lineage_id belongs to a different actor
    - campaigns and actors are not modified by delete
    - requires authentication

  GET /api/campaigns/{id}/actors:
    - returns empty list when campaign has no links
    - returns linked actors with metadata
    - 404 if campaign not found
    - requires authentication

  Invariants:
    - campaign_lineage rows are the only thing written or deleted
    - actor_profiles and campaigns tables are never modified by these endpoints
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_actor(display_name: str = "Test Actor") -> dict:
    resp = client.post("/api/actors", json={"display_name": display_name}, headers=_HEADERS)
    assert resp.status_code == 201
    return resp.json()


def _create_campaign() -> str:
    """Insert a minimal campaign row directly and return its id."""
    cid = str(uuid.uuid4())
    with get_session() as session:
        now = datetime.now(UTC).isoformat()
        session.execute(
            text("""
                INSERT INTO campaigns (id, name, status, first_seen, last_seen,
                                      member_ip_count, confidence, created_at, updated_at)
                VALUES (:id, :name, 'active', :now, :now, 1, 0.8, :now, :now)
            """),
            {"id": cid, "name": f"campaign-{cid[:8]}", "now": now},
        )
    return cid


# ---------------------------------------------------------------------------
# POST /api/actors/{actor_id}/campaigns
# ---------------------------------------------------------------------------


def test_link_campaign_returns_201():
    actor = _create_actor("Alpha")
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 201


def test_link_campaign_response_has_expected_fields():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "temporal_overlap", "confidence": 0.75},
        headers=_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["actor_profile_id"] == actor["id"]
    assert data["campaign_id"] == cid
    assert data["relationship_type"] == "temporal_overlap"
    assert data["confidence"] == 0.75
    assert data["id"] is not None
    assert data["created_at"] is not None


def test_link_campaign_all_valid_relationship_types():
    actor = _create_actor()
    for rel_type in (
        "primary_campaign",
        "infrastructure_reuse",
        "tactic_match",
        "temporal_overlap",
    ):
        cid = _create_campaign()
        resp = client.post(
            f"/api/actors/{actor['id']}/campaigns",
            json={"campaign_id": cid, "relationship_type": rel_type},
            headers=_HEADERS,
        )
        assert resp.status_code == 201, f"failed for rel_type={rel_type!r}: {resp.text}"


def test_link_campaign_404_actor_not_found():
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{uuid.uuid4()}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 404


def test_link_campaign_404_campaign_not_found():
    actor = _create_actor()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": str(uuid.uuid4()), "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 404


def test_link_campaign_422_invalid_relationship_type():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "not_valid"},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


def test_link_campaign_422_confidence_out_of_range():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match", "confidence": 1.5},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


def test_link_campaign_409_duplicate():
    actor = _create_actor()
    cid = _create_campaign()
    payload = {"campaign_id": cid, "relationship_type": "tactic_match"}
    resp1 = client.post(f"/api/actors/{actor['id']}/campaigns", json=payload, headers=_HEADERS)
    assert resp1.status_code == 201
    resp2 = client.post(f"/api/actors/{actor['id']}/campaigns", json=payload, headers=_HEADERS)
    assert resp2.status_code == 409


def test_link_campaign_requires_auth():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/actors/{actor_id}/campaigns
# ---------------------------------------------------------------------------


def test_list_actor_campaigns_empty():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor['id']}/campaigns", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0
    assert data["actor_id"] == actor["id"]


def test_list_actor_campaigns_returns_linked():
    actor = _create_actor()
    cid = _create_campaign()
    client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "infrastructure_reuse"},
        headers=_HEADERS,
    )
    resp = client.get(f"/api/actors/{actor['id']}/campaigns", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    item = data["items"][0]
    assert item["campaign_id"] == cid
    assert item["relationship_type"] == "infrastructure_reuse"
    assert "lineage_id" in item
    assert "linked_at" in item
    assert "campaign_name" in item
    assert "campaign_status" in item


def test_list_actor_campaigns_404_actor_not_found():
    resp = client.get(f"/api/actors/{uuid.uuid4()}/campaigns", headers=_HEADERS)
    assert resp.status_code == 404


def test_list_actor_campaigns_requires_auth():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor['id']}/campaigns")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/actors/{actor_id}/campaigns/{lineage_id}
# ---------------------------------------------------------------------------


def test_delete_actor_campaign_link_returns_204():
    actor = _create_actor()
    cid = _create_campaign()
    link_resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    lineage_id = link_resp.json()["id"]
    resp = client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage_id}", headers=_HEADERS)
    assert resp.status_code == 204


def test_delete_removes_lineage_row():
    actor = _create_actor()
    cid = _create_campaign()
    link_resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    lineage_id = link_resp.json()["id"]
    client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage_id}", headers=_HEADERS)

    list_resp = client.get(f"/api/actors/{actor['id']}/campaigns", headers=_HEADERS)
    assert list_resp.json()["count"] == 0


def test_delete_does_not_modify_actor():
    actor = _create_actor("Stable Actor")
    cid = _create_campaign()
    link_resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    lineage_id = link_resp.json()["id"]
    client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage_id}", headers=_HEADERS)

    actor_resp = client.get(f"/api/actors/{actor['id']}", headers=_HEADERS)
    assert actor_resp.status_code == 200
    assert actor_resp.json()["display_name"] == "Stable Actor"


def test_delete_404_lineage_not_found():
    actor = _create_actor()
    resp = client.delete(f"/api/actors/{actor['id']}/campaigns/{uuid.uuid4()}", headers=_HEADERS)
    assert resp.status_code == 404


def test_delete_404_lineage_belongs_to_different_actor():
    actor_a = _create_actor("Actor A")
    actor_b = _create_actor("Actor B")
    cid = _create_campaign()
    link_resp = client.post(
        f"/api/actors/{actor_a['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    lineage_id = link_resp.json()["id"]

    resp = client.delete(f"/api/actors/{actor_b['id']}/campaigns/{lineage_id}", headers=_HEADERS)
    assert resp.status_code == 404


def test_delete_requires_auth():
    actor = _create_actor()
    cid = _create_campaign()
    link_resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    lineage_id = link_resp.json()["id"]
    resp = client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage_id}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/campaigns/{campaign_id}/actors
# ---------------------------------------------------------------------------


def test_list_campaign_actors_empty():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/actors", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0
    assert data["campaign_id"] == cid


def test_list_campaign_actors_returns_linked():
    actor = _create_actor("Linked Actor")
    cid = _create_campaign()
    client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "primary_campaign", "confidence": 0.9},
        headers=_HEADERS,
    )
    resp = client.get(f"/api/campaigns/{cid}/actors", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    item = data["items"][0]
    assert item["actor_profile_id"] == actor["id"]
    assert item["relationship_type"] == "primary_campaign"
    assert item["confidence"] == 0.9
    assert "lineage_id" in item
    assert "actor_display_name" in item
    assert "actor_status" in item


def test_list_campaign_actors_404_campaign_not_found():
    resp = client.get(f"/api/campaigns/{uuid.uuid4()}/actors", headers=_HEADERS)
    assert resp.status_code == 404


def test_list_campaign_actors_requires_auth():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/actors")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invariant: actor/campaign tables not modified by link operations
# ---------------------------------------------------------------------------


def test_link_operations_do_not_modify_campaign():
    actor = _create_actor()
    cid = _create_campaign()

    with get_session() as session:
        campaign_before = EventRepository(session).get_campaign(cid)

    link_resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    lineage_id = link_resp.json()["id"]
    client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage_id}", headers=_HEADERS)

    with get_session() as session:
        campaign_after = EventRepository(session).get_campaign(cid)

    assert campaign_before["name"] == campaign_after["name"]
    assert campaign_before["status"] == campaign_after["status"]
