"""Unit tests for app/intelligence/actor_stability.py — Phase 7 Group B4.

Tests are pure: no database, no HTTP, no I/O.

Coverage:
  aggregate_actor_stability:
    - empty campaign list → no_linked_campaigns status, null aggregates
    - single campaign with stability → ok status, correct composite/dimensions
    - campaign with NULL stability_json → counted as missing
    - campaign with status 'insufficient_data' → counted as missing
    - all missing → no_stability_data status
    - partial data → partial_data status
    - all present → ok status
    - composite min/max/mean computed correctly
    - per-dimension min/max/mean computed correctly
    - None dimension values excluded from aggregate (not zero-padded)
    - contributors include all campaigns (missing and present)
    - contributor fields are correct for present and missing campaigns
    - dimension_stability is None when no dimensions present
    - actor_composite_stability is None when no composite scores

  Invariants:
    - no AI imports in module
    - no database imports in module
"""

from __future__ import annotations

import json

from app.intelligence.actor_stability import aggregate_actor_stability

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stability_json(
    *,
    status: str = "ok",
    composite: float = 0.80,
    timing: float | None = 0.78,
    sequence: float | None = 0.85,
    protocol: float | None = 0.76,
    credential: float | None = 0.70,
    target: float | None = 0.82,
    sample_count: int = 10,
    calculated_at: str = "2026-05-01T00:00:00+00:00",
) -> str:
    return json.dumps(
        {
            "status": status,
            "composite_score": composite,
            "timing_stability": timing,
            "sequence_stability": sequence,
            "protocol_stability": protocol,
            "credential_stability": credential,
            "target_stability": target,
            "sample_count": sample_count,
            "pair_count": sample_count - 1,
            "dimensions_used": sum(
                v is not None for v in [timing, sequence, protocol, credential, target]
            ),
            "calculated_at": calculated_at,
            "explanation": {},
        }
    )


def _row(
    cid: str = "c1",
    rel: str = "primary_campaign",
    stability_json: str | None = None,
) -> dict:
    return {
        "campaign_id": cid,
        "relationship_type": rel,
        "confidence": 0.8,
        "campaign_name": f"campaign-{cid}",
        "campaign_status": "active",
        "last_seen": "2026-05-01T00:00:00+00:00",
        "behavioral_stability_json": stability_json,
    }


# ---------------------------------------------------------------------------
# Empty / trivial cases
# ---------------------------------------------------------------------------


def test_empty_list_status():
    result = aggregate_actor_stability([])
    assert result["status"] == "no_linked_campaigns"


def test_empty_list_counts():
    result = aggregate_actor_stability([])
    assert result["linked_campaign_count"] == 0
    assert result["campaigns_with_stability"] == 0
    assert result["campaigns_missing_stability"] == 0


def test_empty_list_null_aggregates():
    result = aggregate_actor_stability([])
    assert result["actor_composite_stability"] is None
    assert result["dimension_stability"] is None
    assert result["contributors"] == []


# ---------------------------------------------------------------------------
# Single campaign cases
# ---------------------------------------------------------------------------


def test_single_campaign_ok_status():
    row = _row("c1", stability_json=_stability_json(composite=0.85))
    result = aggregate_actor_stability([row])
    assert result["status"] == "ok"
    assert result["campaigns_with_stability"] == 1
    assert result["campaigns_missing_stability"] == 0


def test_single_campaign_null_stability_counted_as_missing():
    row = _row("c1", stability_json=None)
    result = aggregate_actor_stability([row])
    assert result["status"] == "no_stability_data"
    assert result["campaigns_missing_stability"] == 1
    assert result["campaigns_with_stability"] == 0


def test_single_campaign_insufficient_data_counted_as_missing():
    row = _row("c1", stability_json=_stability_json(status="insufficient_data", composite=0.0))
    result = aggregate_actor_stability([row])
    assert result["status"] == "no_stability_data"
    assert result["campaigns_missing_stability"] == 1


def test_single_campaign_null_composite_null():
    row = _row("c1", stability_json=None)
    result = aggregate_actor_stability([row])
    assert result["actor_composite_stability"] is None


# ---------------------------------------------------------------------------
# Multi-campaign status
# ---------------------------------------------------------------------------


def test_all_missing_gives_no_stability_data():
    rows = [_row("c1", stability_json=None), _row("c2", stability_json=None)]
    result = aggregate_actor_stability(rows)
    assert result["status"] == "no_stability_data"


def test_partial_missing_gives_partial_data():
    rows = [
        _row("c1", stability_json=_stability_json(composite=0.80)),
        _row("c2", stability_json=None),
    ]
    result = aggregate_actor_stability(rows)
    assert result["status"] == "partial_data"
    assert result["campaigns_with_stability"] == 1
    assert result["campaigns_missing_stability"] == 1


def test_all_present_gives_ok():
    rows = [
        _row("c1", stability_json=_stability_json(composite=0.80)),
        _row("c2", stability_json=_stability_json(composite=0.90)),
    ]
    result = aggregate_actor_stability(rows)
    assert result["status"] == "ok"
    assert result["campaigns_missing_stability"] == 0


# ---------------------------------------------------------------------------
# Aggregate computation
# ---------------------------------------------------------------------------


def test_composite_min_max_mean():
    rows = [
        _row("c1", stability_json=_stability_json(composite=0.70)),
        _row("c2", stability_json=_stability_json(composite=0.80)),
        _row("c3", stability_json=_stability_json(composite=0.90)),
    ]
    result = aggregate_actor_stability(rows)
    agg = result["actor_composite_stability"]
    assert agg["min"] == 0.70
    assert agg["max"] == 0.90
    assert abs(agg["mean"] - 0.80) < 1e-5


def test_composite_single_value_min_equals_max_equals_mean():
    rows = [_row("c1", stability_json=_stability_json(composite=0.75))]
    result = aggregate_actor_stability(rows)
    agg = result["actor_composite_stability"]
    assert agg["min"] == agg["max"] == agg["mean"] == 0.75


def test_dimension_stability_min_max_mean():
    rows = [
        _row("c1", stability_json=_stability_json(timing=0.60)),
        _row("c2", stability_json=_stability_json(timing=0.80)),
        _row("c3", stability_json=_stability_json(timing=1.00)),
    ]
    result = aggregate_actor_stability(rows)
    t = result["dimension_stability"]["timing"]
    assert t["min"] == 0.60
    assert t["max"] == 1.00
    assert abs(t["mean"] - 0.80) < 1e-5


def test_none_dimension_excluded_from_aggregate():
    rows = [
        _row("c1", stability_json=_stability_json(protocol=None)),
        _row("c2", stability_json=_stability_json(protocol=None)),
    ]
    result = aggregate_actor_stability(rows)
    dim = result["dimension_stability"]
    assert dim is None or "protocol" not in dim


def test_mixed_none_and_value_dimension():
    rows = [
        _row("c1", stability_json=_stability_json(protocol=0.75)),
        _row("c2", stability_json=_stability_json(protocol=None)),
    ]
    result = aggregate_actor_stability(rows)
    # Only one campaign contributed; protocol should still appear
    assert result["dimension_stability"]["protocol"]["mean"] == 0.75


def test_dimension_stability_none_when_all_dimensions_null():
    rows = [
        _row(
            "c1",
            stability_json=_stability_json(
                timing=None,
                sequence=None,
                protocol=None,
                credential=None,
                target=None,
            ),
        )
    ]
    result = aggregate_actor_stability(rows)
    # All dimensions null — dimension_stability should be None or empty
    assert result["dimension_stability"] is None


# ---------------------------------------------------------------------------
# Contributors
# ---------------------------------------------------------------------------


def test_contributors_count_matches_total_campaigns():
    rows = [
        _row("c1", stability_json=_stability_json(composite=0.80)),
        _row("c2", stability_json=None),
        _row("c3", stability_json=_stability_json(composite=0.90)),
    ]
    result = aggregate_actor_stability(rows)
    assert len(result["contributors"]) == 3


def test_present_contributor_has_composite_score():
    row = _row("c1", stability_json=_stability_json(composite=0.85))
    result = aggregate_actor_stability([row])
    contrib = result["contributors"][0]
    assert contrib["composite_score"] == 0.85


def test_missing_contributor_has_null_composite_score():
    row = _row("c1", stability_json=None)
    result = aggregate_actor_stability([row])
    contrib = result["contributors"][0]
    assert contrib["composite_score"] is None


def test_contributor_fields_present():
    row = _row("c1", "primary_campaign", _stability_json(composite=0.80, sample_count=12))
    result = aggregate_actor_stability([row])
    contrib = result["contributors"][0]
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


def test_contributor_relationship_type_preserved():
    row = _row("c1", "infrastructure_reuse", _stability_json(composite=0.80))
    result = aggregate_actor_stability([row])
    assert result["contributors"][0]["relationship_type"] == "infrastructure_reuse"


def test_missing_contributor_status_no_data():
    row = _row("c1", stability_json=None)
    result = aggregate_actor_stability([row])
    assert result["contributors"][0]["status"] == "no_data"


def test_missing_contributor_status_insufficient_data():
    row = _row("c1", stability_json=_stability_json(status="insufficient_data", composite=0.0))
    result = aggregate_actor_stability([row])
    assert result["contributors"][0]["status"] == "insufficient_data"


# ---------------------------------------------------------------------------
# Unparseable JSON
# ---------------------------------------------------------------------------


def test_unparseable_stability_json_counted_as_missing():
    row = _row("c1", stability_json="not-valid-json{{{")
    result = aggregate_actor_stability([row])
    assert result["campaigns_missing_stability"] == 1
    assert result["status"] == "no_stability_data"


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_no_ai_imports_in_actor_stability():
    import inspect

    import app.intelligence.actor_stability as mod

    src = inspect.getsource(mod)
    assert "from app.ai" not in src
    assert "import app.ai" not in src
    assert "openai" not in src.lower()
    assert "anthropic" not in src.lower()


def test_no_db_imports_in_actor_stability():
    import inspect

    import app.intelligence.actor_stability as mod

    src = inspect.getsource(mod)
    assert "get_session" not in src
    assert "EventRepository" not in src
    assert "from app.db" not in src
