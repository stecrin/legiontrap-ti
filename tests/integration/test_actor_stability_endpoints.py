"""Integration tests for Phase 7 Group B4 — GET /api/actors/{id}/stability.

Tests hit the full stack: FastAPI TestClient → routers → EventRepository → SQLite.

Coverage:
  GET /api/actors/{id}/stability:
    - requires authentication (401 without key)
    - unknown actor returns 404
    - actor with no linked campaigns returns no_linked_campaigns status
    - response has all expected top-level keys
    - actor_id and actor_display_name present
    - campaigns_with_stability counted correctly
    - campaigns_missing_stability counted correctly
    - partial_data status when some campaigns lack stability
    - no_stability_data status when all campaigns lack stability
    - ok status when all campaigns have stability
    - actor_composite_stability has min/max/mean when data present
    - actor_composite_stability is null when no data
    - dimension_stability is null when no data
    - contributors list contains all linked campaigns
    - contributors include missing campaigns with null composite_score
    - endpoint never writes to actor_profiles
    - endpoint never writes to campaign_lineage
    - endpoint never writes to campaigns
    - no AI imports in router
    - no federation imports in router
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.main import app

client = TestClient(app)

_API_KEY = "test-key"
_HEADERS = {"X-API-Key": _API_KEY}
_TS = "2026-05-01T12:00:00+00:00"


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("API_KEY", _API_KEY)
    monkeypatch.setenv("FEED_SALT", "test-salt")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _make_stability_json(composite: float = 0.80) -> str:
    return json.dumps(
        {
            "status": "ok",
            "composite_score": composite,
            "timing_stability": 0.78,
            "sequence_stability": 0.85,
            "protocol_stability": None,
            "credential_stability": None,
            "target_stability": None,
            "sample_count": 5,
            "pair_count": 4,
            "dimensions_used": 2,
            "calculated_at": "2026-05-01T12:00:00+00:00",
            "explanation": {},
        }
    )


def _create_campaign(
    *,
    status: str = "active",
    behavioral_stability_json: str | None = None,
) -> str:
    cid = _uid()
    with get_session() as session:
        from sqlalchemy import text

        session.execute(
            text("""
                INSERT INTO campaigns (
                    id, name, status, confidence,
                    first_seen, last_seen, member_ip_count,
                    behavioral_stability_json,
                    created_at, updated_at
                ) VALUES (
                    :id, :name, :status, 0.7,
                    :ts, :ts, 1,
                    :stab_json,
                    :ts, :ts
                )
            """),
            {
                "id": cid,
                "name": f"campaign-{cid[:8]}",
                "status": status,
                "ts": _TS,
                "stab_json": behavioral_stability_json,
            },
        )
    return cid


def _create_actor(display_name: str = "Test Actor") -> str:
    aid = _uid()
    with get_session() as session:
        EventRepository(session).create_actor_profile(
            actor_id=aid,
            display_name=display_name,
            created_at=_TS,
        )
    return aid


def _link(actor_id: str, campaign_id: str, rel: str = "temporal_overlap") -> None:
    with get_session() as session:
        EventRepository(session).link_campaign_to_actor(
            actor_profile_id=actor_id,
            campaign_id=campaign_id,
            relationship_type=rel,
        )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_stability_requires_auth():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor}/stability")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 404 handling
# ---------------------------------------------------------------------------


def test_unknown_actor_returns_404():
    resp = client.get(f"/api/actors/{_uid()}/stability", headers=_HEADERS)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------


def test_no_linked_campaigns_returns_200():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    assert resp.status_code == 200


def test_no_linked_campaigns_status():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["status"] == "no_linked_campaigns"


def test_response_has_expected_top_level_keys():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    expected_keys = {
        "actor_id",
        "actor_display_name",
        "linked_campaign_count",
        "campaigns_with_stability",
        "campaigns_missing_stability",
        "actor_composite_stability",
        "dimension_stability",
        "contributors",
        "status",
        "computed_at",
    }
    assert expected_keys.issubset(data.keys()), f"missing keys: {expected_keys - set(data.keys())}"


def test_actor_id_and_display_name_in_response():
    actor = _create_actor("Operator Group Alpha")
    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["actor_id"] == actor
    assert data["actor_display_name"] == "Operator Group Alpha"


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_no_stability_data_status():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=None)
    _link(actor, cid)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["status"] == "no_stability_data"
    assert data["campaigns_missing_stability"] == 1
    assert data["campaigns_with_stability"] == 0


def test_partial_data_status():
    actor = _create_actor()
    c1 = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    c2 = _create_campaign(behavioral_stability_json=None)
    _link(actor, c1)
    _link(actor, c2)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["status"] == "partial_data"
    assert data["campaigns_with_stability"] == 1
    assert data["campaigns_missing_stability"] == 1


def test_ok_status_all_have_stability():
    actor = _create_actor()
    c1 = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    c2 = _create_campaign(behavioral_stability_json=_make_stability_json(0.90))
    _link(actor, c1)
    _link(actor, c2)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["status"] == "ok"
    assert data["campaigns_missing_stability"] == 0


# ---------------------------------------------------------------------------
# Aggregate values
# ---------------------------------------------------------------------------


def test_composite_stability_present_when_data_exists():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    _link(actor, cid)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    agg = data["actor_composite_stability"]
    assert agg is not None
    assert "min" in agg
    assert "max" in agg
    assert "mean" in agg


def test_composite_stability_null_when_no_data():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=None)
    _link(actor, cid)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["actor_composite_stability"] is None


def test_composite_min_max_mean_correct():
    actor = _create_actor()
    for composite in [0.70, 0.80, 0.90]:
        cid = _create_campaign(behavioral_stability_json=_make_stability_json(composite))
        _link(actor, cid)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    agg = data["actor_composite_stability"]
    assert abs(agg["min"] - 0.70) < 1e-4
    assert abs(agg["max"] - 0.90) < 1e-4
    assert abs(agg["mean"] - 0.80) < 1e-4


def test_dimension_stability_present_when_data_exists():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    _link(actor, cid)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["dimension_stability"] is not None


def test_dimension_stability_null_when_no_data():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=None)
    _link(actor, cid)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["dimension_stability"] is None


# ---------------------------------------------------------------------------
# Contributors
# ---------------------------------------------------------------------------


def test_contributors_count_matches_linked_campaigns():
    actor = _create_actor()
    c1 = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    c2 = _create_campaign(behavioral_stability_json=None)
    c3 = _create_campaign(behavioral_stability_json=_make_stability_json(0.90))
    _link(actor, c1)
    _link(actor, c2)
    _link(actor, c3)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert len(data["contributors"]) == 3


def test_contributors_include_missing_campaigns():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=None)
    _link(actor, cid)

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert len(data["contributors"]) == 1
    assert data["contributors"][0]["composite_score"] is None


def test_contributors_have_expected_keys():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=_make_stability_json(0.85))
    _link(actor, cid, rel="primary_campaign")

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    contrib = data["contributors"][0]
    for key in (
        "campaign_id",
        "campaign_name",
        "relationship_type",
        "composite_score",
        "status",
        "sample_count",
        "last_computed",
    ):
        assert key in contrib, f"missing key: {key!r}"


def test_contributor_relationship_type_present():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    _link(actor, cid, rel="infrastructure_reuse")

    resp = client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)
    data = resp.json()
    assert data["contributors"][0]["relationship_type"] == "infrastructure_reuse"


# ---------------------------------------------------------------------------
# No-write invariants
# ---------------------------------------------------------------------------


def test_stability_does_not_write_to_actor_profiles():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    _link(actor, cid)

    with get_session() as session:
        before = EventRepository(session).list_actor_profiles()

    client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)

    with get_session() as session:
        after = EventRepository(session).list_actor_profiles()

    assert len(before) == len(after)
    assert before[0]["updated_at"] == after[0]["updated_at"]


def test_stability_does_not_write_to_campaign_lineage():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    _link(actor, cid)

    with get_session() as session:
        before = EventRepository(session).list_campaign_lineage()

    client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)

    with get_session() as session:
        after = EventRepository(session).list_campaign_lineage()

    assert len(before) == len(after)


def test_stability_does_not_write_to_campaigns():
    actor = _create_actor()
    cid = _create_campaign(behavioral_stability_json=_make_stability_json(0.80))
    _link(actor, cid)

    with get_session() as session:
        from sqlalchemy import text

        before_row = session.execute(
            text("SELECT updated_at FROM campaigns WHERE id = :id"), {"id": cid}
        ).fetchone()

    client.get(f"/api/actors/{actor}/stability", headers=_HEADERS)

    with get_session() as session:
        from sqlalchemy import text

        after_row = session.execute(
            text("SELECT updated_at FROM campaigns WHERE id = :id"), {"id": cid}
        ).fetchone()

    assert before_row[0] == after_row[0]


# ---------------------------------------------------------------------------
# Router invariants
# ---------------------------------------------------------------------------


def test_no_ai_imports_in_actors_router():
    import inspect

    import app.routers.actors as mod

    src = inspect.getsource(mod)
    assert "from app.ai" not in src
    assert "import app.ai" not in src


def test_no_federation_imports_in_actors_router():
    import inspect

    import app.routers.actors as mod

    src = inspect.getsource(mod)
    assert "from app.routers.federation" not in src
    assert "import federation" not in src
