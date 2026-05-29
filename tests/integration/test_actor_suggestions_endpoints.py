"""Integration tests for Phase 7 Group B3 — GET /api/actors/suggestions.

Tests hit the full stack: FastAPI TestClient → routers → EventRepository → SQLite.

Coverage:
  GET /api/actors/suggestions:
    - requires authentication (401 without key)
    - returns 200 with expected response shape when no campaigns
    - returns empty suggestions when no campaigns have fingerprints
    - returns empty suggestions when only one campaign has a fingerprint
    - returns a suggestion when two similar campaigns exist
    - suggestion contains all expected fields
    - suggestion contains campaign_a and campaign_b summaries
    - suggestion breakdown has per-dimension scores
    - coattributed pair is excluded from suggestions
    - min_score query param overrides config default
    - limit query param overrides config default
    - /suggestions route does not conflict with /{actor_id} route

  Invariants:
    - GET /suggestions never writes to actor_profiles
    - GET /suggestions never writes to campaign_lineage
    - suggested_relationship_type is advisory (one of valid types)
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES
from app.main import app

client = TestClient(app)

_API_KEY = "test-key"
_HEADERS = {"X-API-Key": _API_KEY}


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setenv("API_KEY", _API_KEY)
    monkeypatch.setenv("FEED_SALT", "test-salt")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


_TS = "2026-05-01T12:00:00+00:00"

_TIMING_FEATURES_A = json.dumps(
    {
        "interval": {"mean": 60.0, "stddev": 5.0, "p25": 55.0, "p75": 65.0, "p95": 70.0},
        "burst_cv": 0.1,
    }
)
_SEQ_FEATURES_A = json.dumps({"port_sequence": [22, 80, 443]})

_REP_FP_A = json.dumps(
    {
        "timing_features": _TIMING_FEATURES_A,
        "sequence_features": _SEQ_FEATURES_A,
        "protocol_features": None,
        "credential_features": None,
        "target_features": None,
    }
)

_REP_FP_B = json.dumps(
    {
        "timing_features": _TIMING_FEATURES_A,
        "sequence_features": _SEQ_FEATURES_A,
        "protocol_features": None,
        "credential_features": None,
        "target_features": None,
    }
)

_REP_FP_DIFFERENT = json.dumps(
    {
        "timing_features": json.dumps(
            {
                "interval": {
                    "mean": 3600.0,
                    "stddev": 200.0,
                    "p25": 3400.0,
                    "p75": 3800.0,
                    "p95": 3900.0,
                },
                "burst_cv": 0.9,
            }
        ),
        "sequence_features": json.dumps({"port_sequence": [8080, 3389, 5900]}),
        "protocol_features": None,
        "credential_features": None,
        "target_features": None,
    }
)


def _create_campaign(
    *,
    status: str = "active",
    representative_fingerprint_json: str | None = None,
) -> str:
    cid = _uid()
    with get_session() as session:
        from sqlalchemy import text

        session.execute(
            text("""
                INSERT INTO campaigns (
                    id, name, status, confidence,
                    first_seen, last_seen, member_ip_count,
                    representative_fingerprint_json,
                    created_at, updated_at
                ) VALUES (
                    :id, :name, :status, 0.7,
                    :ts, :ts, 1,
                    :fp_json,
                    :ts, :ts
                )
            """),
            {
                "id": cid,
                "name": f"campaign-{cid[:8]}",
                "status": status,
                "ts": _TS,
                "fp_json": representative_fingerprint_json,
            },
        )
    return cid


def _create_actor() -> str:
    aid = _uid()
    with get_session() as session:
        EventRepository(session).create_actor_profile(
            actor_id=aid,
            display_name=f"actor-{aid[:8]}",
            created_at=_TS,
        )
    return aid


def _link_campaign(actor_id: str, campaign_id: str) -> None:
    with get_session() as session:
        EventRepository(session).link_campaign_to_actor(
            actor_profile_id=actor_id,
            campaign_id=campaign_id,
            relationship_type="temporal_overlap",
        )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_suggestions_requires_auth():
    resp = client.get("/api/actors/suggestions")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Empty / sparse states
# ---------------------------------------------------------------------------


def test_suggestions_no_campaigns_returns_200():
    resp = client.get("/api/actors/suggestions", headers=_HEADERS)
    assert resp.status_code == 200


def test_suggestions_no_campaigns_empty_list():
    resp = client.get("/api/actors/suggestions", headers=_HEADERS)
    data = resp.json()
    assert data["suggestions"] == []
    assert data["count"] == 0
    assert data["campaigns_evaluated"] == 0
    assert data["total_pairs_evaluated"] == 0


def test_suggestions_no_fingerprints_returns_empty():
    _create_campaign(status="active", representative_fingerprint_json=None)
    _create_campaign(status="active", representative_fingerprint_json=None)
    resp = client.get("/api/actors/suggestions", headers=_HEADERS)
    data = resp.json()
    assert data["suggestions"] == []
    assert data["campaigns_evaluated"] == 0


def test_suggestions_single_fingerprinted_campaign_returns_empty():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    resp = client.get("/api/actors/suggestions", headers=_HEADERS)
    data = resp.json()
    assert data["suggestions"] == []
    assert data["total_pairs_evaluated"] == 0


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------


def test_suggestions_response_has_expected_top_level_keys():
    resp = client.get("/api/actors/suggestions", headers=_HEADERS)
    data = resp.json()
    assert set(data.keys()) == {
        "suggestions",
        "count",
        "total_pairs_evaluated",
        "min_score_applied",
        "campaigns_evaluated",
    }


def test_suggestions_min_score_applied_matches_default():
    resp = client.get("/api/actors/suggestions", headers=_HEADERS)
    data = resp.json()
    assert isinstance(data["min_score_applied"], float)
    # Default from config — just verify it's a valid threshold
    assert 0.0 < data["min_score_applied"] <= 1.0


# ---------------------------------------------------------------------------
# Suggestion result when similar campaigns exist
# ---------------------------------------------------------------------------


def test_suggestions_returns_suggestion_for_identical_fingerprints():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    assert data["count"] >= 1
    assert data["total_pairs_evaluated"] >= 1


def test_suggestion_item_has_expected_keys():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    assert data["count"] >= 1
    s = data["suggestions"][0]
    assert set(s.keys()) == {
        "campaign_a",
        "campaign_b",
        "similarity_score",
        "score_breakdown",
        "suggested_relationship_type",
    }


def test_suggestion_campaign_summary_has_expected_keys():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    s = data["suggestions"][0]
    for side in ("campaign_a", "campaign_b"):
        for key in ("id", "name", "status", "last_seen", "member_ip_count"):
            assert key in s[side], f"missing {key!r} in {side}"


def test_suggestion_breakdown_has_dimension_scores():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    breakdown = data["suggestions"][0]["score_breakdown"]
    for key in (
        "timing_similarity",
        "sequence_similarity",
        "protocol_similarity",
        "credential_similarity",
        "target_similarity",
        "weighted_total",
        "dimensions_used",
    ):
        assert key in breakdown


def test_suggestion_relationship_type_is_valid():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    rtype = data["suggestions"][0]["suggested_relationship_type"]
    assert rtype in VALID_RELATIONSHIP_TYPES


def test_suggestion_similarity_score_is_float():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    score = data["suggestions"][0]["similarity_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Coattribution exclusion
# ---------------------------------------------------------------------------


def test_coattributed_pair_excluded_from_suggestions():
    c1 = _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    c2 = _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    actor = _create_actor()
    _link_campaign(actor, c1)
    _link_campaign(actor, c2)

    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    pair_ids = {
        frozenset({s["campaign_a"]["id"], s["campaign_b"]["id"]}) for s in data["suggestions"]
    }
    assert frozenset({c1, c2}) not in pair_ids
    assert data["total_pairs_evaluated"] == 0


def test_non_coattributed_pair_not_excluded():
    c1 = _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    c2 = _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    actor = _create_actor()
    _link_campaign(actor, c1)
    _link_campaign(actor, c2)
    # third campaign is not linked; (c1,c3) and (c2,c3) should still be evaluated

    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0},
        headers=_HEADERS,
    )
    data = resp.json()
    assert data["total_pairs_evaluated"] == 2


# ---------------------------------------------------------------------------
# Query param overrides
# ---------------------------------------------------------------------------


def test_min_score_query_param_filters_dissimilar_pair():
    # _REP_FP_A and _REP_FP_DIFFERENT have very different timing and sequences
    # so their similarity is well below 1.0; a min_score=1.0 should exclude them.
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_DIFFERENT)
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 1.0},
        headers=_HEADERS,
    )
    data = resp.json()
    assert data["count"] == 0
    assert data["min_score_applied"] == 1.0


def test_limit_query_param_caps_results():
    for _ in range(4):
        _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)

    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 0.0, "limit": 2},
        headers=_HEADERS,
    )
    data = resp.json()
    assert data["count"] <= 2
    assert len(data["suggestions"]) <= 2


def test_limit_invalid_returns_422():
    resp = client.get(
        "/api/actors/suggestions",
        params={"limit": 0},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


def test_min_score_out_of_range_returns_422():
    resp = client.get(
        "/api/actors/suggestions",
        params={"min_score": 1.5},
        headers=_HEADERS,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Route ordering invariant — /suggestions must not conflict with /{actor_id}
# ---------------------------------------------------------------------------


def test_suggestions_route_does_not_shadow_actor_id_route():
    actor = _create_actor()
    resp = client.get(f"/api/actors/{actor}", headers=_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == actor


def test_suggestions_path_not_treated_as_actor_id():
    resp = client.get("/api/actors/suggestions", headers=_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "suggestions" in data


# ---------------------------------------------------------------------------
# No-write invariant
# ---------------------------------------------------------------------------


def test_suggestions_does_not_write_to_actor_profiles():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)

    with get_session() as session:
        before = EventRepository(session).list_actor_profiles()

    client.get("/api/actors/suggestions", params={"min_score": 0.0}, headers=_HEADERS)

    with get_session() as session:
        after = EventRepository(session).list_actor_profiles()

    assert len(before) == len(after)


def test_suggestions_does_not_write_to_campaign_lineage():
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_A)
    _create_campaign(status="active", representative_fingerprint_json=_REP_FP_B)

    with get_session() as session:
        before = EventRepository(session).list_campaign_lineage()

    client.get("/api/actors/suggestions", params={"min_score": 0.0}, headers=_HEADERS)

    with get_session() as session:
        after = EventRepository(session).list_campaign_lineage()

    assert len(before) == len(after)
