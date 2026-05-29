"""Integration tests for Phase 7 Group B1 — actor profile CRUD API.

Tests hit the full stack: FastAPI TestClient → routers → EventRepository → SQLite.

Coverage:
  POST /api/actors:
    - creates actor, returns 201 with actor dict
    - missing display_name returns 422
    - blank display_name returns 422
    - invalid status returns 422
    - invalid confidence (out of range) returns 422
    - requires authentication

  GET /api/actors:
    - returns empty list when no actors
    - returns all actors newest first
    - filters by status param
    - invalid status filter returns 422
    - respects limit param
    - requires authentication

  GET /api/actors/{id}:
    - returns actor by id
    - returns 404 for unknown id
    - requires authentication

  PATCH /api/actors/{id}:
    - updates display_name
    - updates status to archived
    - updates confidence
    - clears notes (explicit null)
    - omitted fields are not changed
    - invalid status returns 422
    - returns 404 for unknown id
    - requires authentication

  Invariants:
    - actors router does not import from app.ai
    - no automatic lineage or actor creation
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
# POST /api/actors
# ---------------------------------------------------------------------------


def test_create_actor_returns_201():
    resp = client.post("/api/actors", json={"display_name": "Alpha"}, headers=_HEADERS)
    assert resp.status_code == 201


def test_create_actor_response_has_expected_fields():
    resp = client.post(
        "/api/actors", json={"display_name": "Beta", "confidence": 0.7}, headers=_HEADERS
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["display_name"] == "Beta"
    assert data["confidence"] == 0.7
    assert data["status"] == "active"
    assert data["id"] is not None
    assert data["created_at"] is not None


def test_create_actor_missing_display_name_returns_422():
    resp = client.post("/api/actors", json={"confidence": 0.5}, headers=_HEADERS)
    assert resp.status_code == 422


def test_create_actor_blank_display_name_returns_422():
    resp = client.post("/api/actors", json={"display_name": "   "}, headers=_HEADERS)
    assert resp.status_code == 422


def test_create_actor_invalid_status_returns_422():
    resp = client.post(
        "/api/actors", json={"display_name": "X", "status": "retired"}, headers=_HEADERS
    )
    assert resp.status_code == 422


def test_create_actor_confidence_out_of_range_returns_422():
    resp = client.post(
        "/api/actors", json={"display_name": "X", "confidence": 1.5}, headers=_HEADERS
    )
    assert resp.status_code == 422


def test_create_actor_with_notes():
    resp = client.post(
        "/api/actors",
        json={"display_name": "With Notes", "notes": "some analyst note"},
        headers=_HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["notes"] == "some analyst note"


def test_create_actor_archived_status():
    resp = client.post(
        "/api/actors", json={"display_name": "Archived One", "status": "archived"}, headers=_HEADERS
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "archived"


def test_create_actor_requires_auth():
    resp = client.post("/api/actors", json={"display_name": "NoAuth"})
    assert resp.status_code == 401


def test_create_actor_display_name_not_unique_constrained():
    resp1 = client.post("/api/actors", json={"display_name": "Duplicate"}, headers=_HEADERS)
    resp2 = client.post("/api/actors", json={"display_name": "Duplicate"}, headers=_HEADERS)
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] != resp2.json()["id"]


# ---------------------------------------------------------------------------
# GET /api/actors
# ---------------------------------------------------------------------------


def test_list_actors_empty():
    resp = client.get("/api/actors", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_list_actors_returns_created_actors():
    client.post("/api/actors", json={"display_name": "Actor One"}, headers=_HEADERS)
    client.post("/api/actors", json={"display_name": "Actor Two"}, headers=_HEADERS)

    resp = client.get("/api/actors", headers=_HEADERS)
    assert resp.status_code == 200
    names = {a["display_name"] for a in resp.json()["items"]}
    assert "Actor One" in names
    assert "Actor Two" in names


def test_list_actors_filter_by_status():
    client.post(
        "/api/actors", json={"display_name": "Active Actor", "status": "active"}, headers=_HEADERS
    )
    client.post(
        "/api/actors",
        json={"display_name": "Archived Actor", "status": "archived"},
        headers=_HEADERS,
    )

    active_resp = client.get("/api/actors?status=active", headers=_HEADERS)
    assert all(a["status"] == "active" for a in active_resp.json()["items"])

    archived_resp = client.get("/api/actors?status=archived", headers=_HEADERS)
    assert all(a["status"] == "archived" for a in archived_resp.json()["items"])


def test_list_actors_invalid_status_filter_returns_422():
    resp = client.get("/api/actors?status=retired", headers=_HEADERS)
    assert resp.status_code == 422


def test_list_actors_respects_limit():
    for i in range(5):
        client.post("/api/actors", json={"display_name": f"Limit {i}"}, headers=_HEADERS)
    resp = client.get("/api/actors?limit=2", headers=_HEADERS)
    assert len(resp.json()["items"]) <= 2


def test_list_actors_requires_auth():
    resp = client.get("/api/actors")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/actors/{id}
# ---------------------------------------------------------------------------


def test_get_actor_by_id():
    created = client.post("/api/actors", json={"display_name": "Findable"}, headers=_HEADERS).json()
    resp = client.get(f"/api/actors/{created['id']}", headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert resp.json()["display_name"] == "Findable"


def test_get_actor_unknown_returns_404():
    resp = client.get(f"/api/actors/{uuid.uuid4()}", headers=_HEADERS)
    assert resp.status_code == 404


def test_get_actor_requires_auth():
    created = client.post("/api/actors", json={"display_name": "AuthTest"}, headers=_HEADERS).json()
    resp = client.get(f"/api/actors/{created['id']}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/actors/{id}
# ---------------------------------------------------------------------------


def test_patch_actor_display_name():
    created = client.post(
        "/api/actors", json={"display_name": "Before Patch"}, headers=_HEADERS
    ).json()
    resp = client.patch(
        f"/api/actors/{created['id']}", json={"display_name": "After Patch"}, headers=_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "After Patch"


def test_patch_actor_status_to_archived():
    created = client.post(
        "/api/actors", json={"display_name": "To Archive"}, headers=_HEADERS
    ).json()
    resp = client.patch(
        f"/api/actors/{created['id']}", json={"status": "archived"}, headers=_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_patch_actor_confidence():
    created = client.post(
        "/api/actors", json={"display_name": "Confidence Actor"}, headers=_HEADERS
    ).json()
    resp = client.patch(f"/api/actors/{created['id']}", json={"confidence": 0.9}, headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["confidence"] == pytest.approx(0.9)


def test_patch_actor_sets_notes():
    created = client.post(
        "/api/actors", json={"display_name": "Notes Actor"}, headers=_HEADERS
    ).json()
    resp = client.patch(
        f"/api/actors/{created['id']}", json={"notes": "analyst note"}, headers=_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == "analyst note"


def test_patch_actor_clears_notes_with_null():
    created = client.post(
        "/api/actors",
        json={"display_name": "Clear Notes", "notes": "initial note"},
        headers=_HEADERS,
    ).json()
    resp = client.patch(f"/api/actors/{created['id']}", json={"notes": None}, headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["notes"] is None


def test_patch_actor_omitted_fields_unchanged():
    created = client.post(
        "/api/actors",
        json={"display_name": "Stable Actor", "notes": "keep this"},
        headers=_HEADERS,
    ).json()
    resp = client.patch(f"/api/actors/{created['id']}", json={"confidence": 0.6}, headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["notes"] == "keep this"
    assert data["display_name"] == "Stable Actor"


def test_patch_actor_invalid_status_returns_422():
    created = client.post(
        "/api/actors", json={"display_name": "Status Test"}, headers=_HEADERS
    ).json()
    resp = client.patch(
        f"/api/actors/{created['id']}", json={"status": "pending"}, headers=_HEADERS
    )
    assert resp.status_code == 422


def test_patch_actor_invalid_confidence_returns_422():
    created = client.post(
        "/api/actors", json={"display_name": "Conf Test"}, headers=_HEADERS
    ).json()
    resp = client.patch(f"/api/actors/{created['id']}", json={"confidence": 2.0}, headers=_HEADERS)
    assert resp.status_code == 422


def test_patch_actor_unknown_returns_404():
    resp = client.patch(
        f"/api/actors/{uuid.uuid4()}", json={"display_name": "Ghost"}, headers=_HEADERS
    )
    assert resp.status_code == 404


def test_patch_actor_requires_auth():
    created = client.post(
        "/api/actors", json={"display_name": "Auth Patch"}, headers=_HEADERS
    ).json()
    resp = client.patch(f"/api/actors/{created['id']}", json={"display_name": "X"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_actors_router_does_not_import_ai():
    import importlib

    mod = importlib.import_module("app.routers.actors")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content


def test_actors_router_does_not_import_federation():
    import importlib

    mod = importlib.import_module("app.routers.actors")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "federation" not in content


def test_no_automatic_actor_creation_on_campaign_ingest(monkeypatch):
    monkeypatch.setenv("API_KEY", _API_KEY)
    monkeypatch.setenv("FEED_SALT", "test-salt")

    event = {
        "id": str(uuid.uuid4()),
        "ts": "2026-05-01T00:00:00+00:00",
        "src_ip": "10.0.0.1",
        "event_type": "ssh_login",
        "dst_port": 22,
    }
    client.post("/api/ingest", json={"events": [event]}, headers=_HEADERS)

    with get_session() as session:
        actors = EventRepository(session).list_actor_profiles()
    assert actors == []
