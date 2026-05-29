"""Integration tests for Phase 7 Group B2 — campaign-to-actor linking API.

Tests hit the full stack: FastAPI TestClient → routers → EventRepository → SQLite.

Coverage:
  POST /api/actors/{id}/campaigns:
    - valid link creation returns 201 with lineage record
    - unknown actor returns 404
    - unknown campaign returns 404
    - invalid relationship_type returns 422
    - duplicate (actor, campaign) pair returns 409 with existing_lineage_id
    - confidence out of range returns 422
    - requires authentication

  GET /api/actors/{id}/campaigns:
    - returns linked campaigns with metadata
    - empty list when actor has no links
    - unknown actor returns 404
    - requires authentication

  DELETE /api/actors/{id}/campaigns/{lineage_id}:
    - valid delete returns 204
    - lineage belonging to different actor returns 404
    - unknown lineage_id returns 404
    - does not delete campaign
    - does not delete actor
    - requires authentication

  GET /api/campaigns/{id}/actors:
    - returns linked actors with metadata
    - empty list when campaign has no links
    - unknown campaign returns 404
    - requires authentication

  Invariants:
    - no automatic lineage creation on ingest
    - actors router does not import from app.ai
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

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
    from datetime import UTC, datetime

    cid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with get_session() as session:
        EventRepository(session).create_campaign(
            campaign_id=cid,
            name=f"test-{cid[:8]}",
            status="active",
            confidence=0.7,
            first_seen=now,
            last_seen=now,
            member_ip_count=2,
            created_at=now,
            updated_at=now,
        )
    return cid


def _link(actor_id: str, campaign_id: str, rtype: str = "tactic_match") -> dict:
    resp = client.post(
        f"/api/actors/{actor_id}/campaigns",
        json={"campaign_id": campaign_id, "relationship_type": rtype},
        headers=_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/actors/{id}/campaigns
# ---------------------------------------------------------------------------


def test_link_campaign_returns_201():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "primary_campaign"},
        headers=_HEADERS,
    )
    assert resp.status_code == 201


def test_link_campaign_response_fields():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={
            "campaign_id": cid,
            "relationship_type": "tactic_match",
            "confidence": 0.8,
            "evidence": "observed same port sequence",
        },
        headers=_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["actor_profile_id"] == actor["id"]
    assert data["campaign_id"] == cid
    assert data["relationship_type"] == "tactic_match"
    assert data["confidence"] == pytest.approx(0.8)
    assert data["evidence_json"] == "observed same port sequence"
    assert data["id"] is not None
    assert data["created_at"] is not None


def test_link_all_valid_relationship_types():
    from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

    for rtype in sorted(VALID_RELATIONSHIP_TYPES):
        actor = _create_actor(f"Actor for {rtype}")
        cid = _create_campaign()
        resp = client.post(
            f"/api/actors/{actor['id']}/campaigns",
            json={"campaign_id": cid, "relationship_type": rtype},
            headers=_HEADERS,
        )
        assert resp.status_code == 201, f"Expected 201 for {rtype}, got {resp.status_code}"
        assert resp.json()["relationship_type"] == rtype


def test_link_unknown_actor_returns_404():
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{uuid.uuid4()}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 404


def test_link_unknown_campaign_returns_404():
    actor = _create_actor()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": str(uuid.uuid4()), "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 404


def test_link_invalid_relationship_type_returns_422():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "made_up"},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


def test_link_empty_relationship_type_returns_422():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": ""},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


def test_link_confidence_out_of_range_returns_422():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match", "confidence": 1.5},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


def test_link_duplicate_returns_409():
    actor = _create_actor()
    cid = _create_campaign()
    first = _link(actor["id"], cid, "primary_campaign")

    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["existing_lineage_id"] == first["id"]


def test_link_duplicate_includes_existing_lineage_id_in_response():
    actor = _create_actor()
    cid = _create_campaign()
    first = _link(actor["id"], cid)

    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["existing_lineage_id"] == first["id"]


def test_link_requires_auth():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "tactic_match"},
    )
    assert resp.status_code == 401


def test_link_missing_campaign_id_returns_422():
    actor = _create_actor()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"relationship_type": "tactic_match"},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


def test_link_missing_relationship_type_returns_422():
    actor = _create_actor()
    cid = _create_campaign()
    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/actors/{id}/campaigns
# ---------------------------------------------------------------------------


def test_list_actor_campaigns_returns_200():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor['id']}/campaigns", headers=_HEADERS)
    assert resp.status_code == 200


def test_list_actor_campaigns_empty_when_no_links():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor['id']}/campaigns", headers=_HEADERS)
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_list_actor_campaigns_returns_linked_items():
    actor = _create_actor()
    cid1 = _create_campaign()
    cid2 = _create_campaign()
    _link(actor["id"], cid1, "primary_campaign")
    _link(actor["id"], cid2, "tactic_match")

    resp = client.get(f"/api/actors/{actor['id']}/campaigns", headers=_HEADERS)
    data = resp.json()
    assert data["count"] == 2
    cids = {item["campaign_id"] for item in data["items"]}
    assert cid1 in cids
    assert cid2 in cids


def test_list_actor_campaigns_includes_campaign_metadata():
    actor = _create_actor()
    cid = _create_campaign()
    _link(actor["id"], cid)

    resp = client.get(f"/api/actors/{actor['id']}/campaigns", headers=_HEADERS)
    item = resp.json()["items"][0]
    assert "campaign_name" in item
    assert "campaign_status" in item
    assert "campaign_last_seen" in item
    assert "campaign_has_fingerprint" in item


def test_list_actor_campaigns_unknown_actor_returns_404():
    resp = client.get(f"/api/actors/{uuid.uuid4()}/campaigns", headers=_HEADERS)
    assert resp.status_code == 404


def test_list_actor_campaigns_requires_auth():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor['id']}/campaigns")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/actors/{id}/campaigns/{lineage_id}
# ---------------------------------------------------------------------------


def test_delete_link_returns_204():
    actor = _create_actor()
    cid = _create_campaign()
    lineage = _link(actor["id"], cid)

    resp = client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage['id']}", headers=_HEADERS)
    assert resp.status_code == 204


def test_delete_link_removes_lineage_record():
    actor = _create_actor()
    cid = _create_campaign()
    lineage = _link(actor["id"], cid)

    client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage['id']}", headers=_HEADERS)

    with get_session() as session:
        record = EventRepository(session).get_lineage_record(lineage["id"])
    assert record is None


def test_delete_link_does_not_delete_campaign():
    actor = _create_actor()
    cid = _create_campaign()
    lineage = _link(actor["id"], cid)

    client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage['id']}", headers=_HEADERS)

    with get_session() as session:
        campaign = EventRepository(session).get_campaign(cid)
    assert campaign is not None


def test_delete_link_does_not_delete_actor():
    actor = _create_actor()
    cid = _create_campaign()
    lineage = _link(actor["id"], cid)

    client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage['id']}", headers=_HEADERS)

    resp = client.get(f"/api/actors/{actor['id']}", headers=_HEADERS)
    assert resp.status_code == 200


def test_delete_link_wrong_actor_returns_404():
    actor1 = _create_actor("Actor One")
    actor2 = _create_actor("Actor Two")
    cid = _create_campaign()
    lineage = _link(actor1["id"], cid)

    resp = client.delete(f"/api/actors/{actor2['id']}/campaigns/{lineage['id']}", headers=_HEADERS)
    assert resp.status_code == 404


def test_delete_link_unknown_lineage_returns_404():
    actor = _create_actor()
    resp = client.delete(f"/api/actors/{actor['id']}/campaigns/{uuid.uuid4()}", headers=_HEADERS)
    assert resp.status_code == 404


def test_delete_link_allows_relink_after_deletion():
    actor = _create_actor()
    cid = _create_campaign()
    lineage = _link(actor["id"], cid, "tactic_match")

    client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage['id']}", headers=_HEADERS)

    resp = client.post(
        f"/api/actors/{actor['id']}/campaigns",
        json={"campaign_id": cid, "relationship_type": "primary_campaign"},
        headers=_HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["relationship_type"] == "primary_campaign"


def test_delete_link_requires_auth():
    actor = _create_actor()
    cid = _create_campaign()
    lineage = _link(actor["id"], cid)

    resp = client.delete(f"/api/actors/{actor['id']}/campaigns/{lineage['id']}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/campaigns/{id}/actors
# ---------------------------------------------------------------------------


def test_get_campaign_actors_returns_200():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/actors", headers=_HEADERS)
    assert resp.status_code == 200


def test_get_campaign_actors_empty_when_no_links():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/actors", headers=_HEADERS)
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_get_campaign_actors_returns_linked_actors():
    actor1 = _create_actor("Actor A")
    actor2 = _create_actor("Actor B")
    cid = _create_campaign()
    _link(actor1["id"], cid, "tactic_match")
    _link(actor2["id"], cid, "temporal_overlap")

    resp = client.get(f"/api/campaigns/{cid}/actors", headers=_HEADERS)
    data = resp.json()
    assert data["count"] == 2
    actor_ids = {item["actor_profile_id"] for item in data["items"]}
    assert actor1["id"] in actor_ids
    assert actor2["id"] in actor_ids


def test_get_campaign_actors_includes_actor_metadata():
    actor = _create_actor("Named Actor")
    cid = _create_campaign()
    _link(actor["id"], cid, "primary_campaign")

    resp = client.get(f"/api/campaigns/{cid}/actors", headers=_HEADERS)
    item = resp.json()["items"][0]
    assert item["actor_display_name"] == "Named Actor"
    assert "actor_status" in item
    assert "actor_confidence" in item


def test_get_campaign_actors_includes_relationship_type():
    actor = _create_actor()
    cid = _create_campaign()
    _link(actor["id"], cid, "infrastructure_reuse")

    resp = client.get(f"/api/campaigns/{cid}/actors", headers=_HEADERS)
    assert resp.json()["items"][0]["relationship_type"] == "infrastructure_reuse"


def test_get_campaign_actors_unknown_campaign_returns_404():
    resp = client.get(f"/api/campaigns/{uuid.uuid4()}/actors", headers=_HEADERS)
    assert resp.status_code == 404


def test_get_campaign_actors_requires_auth():
    cid = _create_campaign()
    resp = client.get(f"/api/campaigns/{cid}/actors")
    assert resp.status_code == 401


def test_get_campaign_actors_only_returns_own_campaign_links():
    actor = _create_actor()
    cid1 = _create_campaign()
    cid2 = _create_campaign()
    _link(actor["id"], cid1)

    resp = client.get(f"/api/campaigns/{cid2}/actors", headers=_HEADERS)
    assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_no_automatic_lineage_on_ingest():
    event = {
        "id": str(uuid.uuid4()),
        "ts": "2026-05-01T00:00:00+00:00",
        "src_ip": "10.0.0.1",
        "event_type": "ssh_login",
        "dst_port": 22,
    }
    client.post("/api/ingest", json={"events": [event]}, headers=_HEADERS)

    with get_session() as session:
        lineage = EventRepository(session).list_campaign_lineage()
    assert lineage == []


def test_actors_router_does_not_import_ai():
    import importlib

    mod = importlib.import_module("app.routers.actors")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content
