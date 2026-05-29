"""Unit tests for app/intelligence/actor_suggestions.py — Phase 7 Group B3.

Tests are pure: no database, no HTTP, no I/O.

Coverage:
  _derive_relationship_type:
    - sequence >= 0.85 AND timing >= 0.80  → primary_campaign
    - timing   >= 0.80 AND sequence < 0.70 → infrastructure_reuse
    - protocol >= 0.80                     → tactic_match
    - default fallback                     → temporal_overlap
    - None dimension values treated as 0.0

  build_actor_suggestions:
    - empty campaigns list → 0 suggestions, 0 pairs evaluated
    - single campaign → 0 suggestions, 0 pairs evaluated
    - coattributed pair skipped, not counted in total_pairs_evaluated
    - pair below min_score → not in suggestions
    - pair above min_score → appears in suggestions with expected fields
    - suggestions sorted by similarity_score DESC
    - limit caps result count
    - limit does not affect total_pairs_evaluated
    - suggested_relationship_type is advisory (present in response)
    - no writes occur (pure function)
    - no AI imports in module
"""

from __future__ import annotations

from unittest.mock import patch

from app.intelligence.actor_suggestions import (
    _derive_relationship_type,
    build_actor_suggestions,
)
from app.intelligence.similarity import SimilarityResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    *,
    timing: float | None = None,
    sequence: float | None = None,
    protocol: float | None = None,
    credential: float | None = None,
    target: float | None = None,
    total: float = 0.0,
) -> SimilarityResult:
    dims = sum(v is not None for v in [timing, sequence, protocol, credential, target])
    return SimilarityResult(
        timing_similarity=timing,
        sequence_similarity=sequence,
        protocol_similarity=protocol,
        credential_similarity=credential,
        target_similarity=target,
        weighted_total=total,
        dimensions_used=dims,
    )


def _make_campaign(cid: str, name: str = "c") -> dict:
    return {
        "id": cid,
        "name": name,
        "status": "active",
        "last_seen": "2026-05-01T00:00:00+00:00",
        "member_ip_count": 1,
        "timing_features": None,
        "sequence_features": None,
        "protocol_features": None,
        "credential_features": None,
        "target_features": None,
    }


# ---------------------------------------------------------------------------
# _derive_relationship_type
# ---------------------------------------------------------------------------


def test_derive_primary_campaign():
    result = _make_result(sequence=0.90, timing=0.85, total=0.90)
    assert _derive_relationship_type(result) == "primary_campaign"


def test_derive_primary_campaign_boundary():
    result = _make_result(sequence=0.85, timing=0.80, total=0.85)
    assert _derive_relationship_type(result) == "primary_campaign"


def test_derive_infrastructure_reuse():
    result = _make_result(timing=0.85, sequence=0.60, total=0.75)
    assert _derive_relationship_type(result) == "infrastructure_reuse"


def test_derive_infrastructure_reuse_boundary():
    result = _make_result(timing=0.80, sequence=0.69, total=0.76)
    assert _derive_relationship_type(result) == "infrastructure_reuse"


def test_derive_tactic_match():
    result = _make_result(timing=0.50, sequence=0.40, protocol=0.82, total=0.60)
    assert _derive_relationship_type(result) == "tactic_match"


def test_derive_temporal_overlap_default():
    result = _make_result(timing=0.60, sequence=0.65, protocol=0.55, total=0.62)
    assert _derive_relationship_type(result) == "temporal_overlap"


def test_derive_none_dimensions_treated_as_zero():
    result = _make_result(timing=None, sequence=None, protocol=None, total=0.50)
    assert _derive_relationship_type(result) == "temporal_overlap"


def test_derive_primary_campaign_takes_precedence_over_tactic_match():
    result = _make_result(sequence=0.90, timing=0.85, protocol=0.90, total=0.90)
    assert _derive_relationship_type(result) == "primary_campaign"


# ---------------------------------------------------------------------------
# build_actor_suggestions — empty / trivial cases
# ---------------------------------------------------------------------------


def test_build_no_campaigns():
    suggestions, total = build_actor_suggestions([], set(), min_score=0.85, limit=20)
    assert suggestions == []
    assert total == 0


def test_build_single_campaign():
    suggestions, total = build_actor_suggestions(
        [_make_campaign("c1")], set(), min_score=0.85, limit=20
    )
    assert suggestions == []
    assert total == 0


# ---------------------------------------------------------------------------
# build_actor_suggestions — filtering and skipping
# ---------------------------------------------------------------------------


def test_build_coattributed_pair_skipped():
    c1 = _make_campaign("c1")
    c2 = _make_campaign("c2")
    coattributed = {frozenset({"c1", "c2"})}

    with patch("app.intelligence.actor_suggestions.compute_weighted_similarity") as mock_sim:
        suggestions, total = build_actor_suggestions(
            [c1, c2], coattributed, min_score=0.0, limit=20
        )
        mock_sim.assert_not_called()

    assert suggestions == []
    assert total == 0


def test_build_coattributed_pair_not_counted_in_total():
    c1 = _make_campaign("c1")
    c2 = _make_campaign("c2")
    c3 = _make_campaign("c3")
    coattributed = {frozenset({"c1", "c2"})}

    high = _make_result(total=0.90)
    with patch(
        "app.intelligence.actor_suggestions.compute_weighted_similarity",
        return_value=high,
    ):
        suggestions, total = build_actor_suggestions(
            [c1, c2, c3], coattributed, min_score=0.0, limit=20
        )

    # Only (c1,c3) and (c2,c3) are evaluated; (c1,c2) is coattributed
    assert total == 2


def test_build_pair_below_min_score_not_in_suggestions():
    c1 = _make_campaign("c1")
    c2 = _make_campaign("c2")
    low = _make_result(total=0.70)

    with patch(
        "app.intelligence.actor_suggestions.compute_weighted_similarity",
        return_value=low,
    ):
        suggestions, total = build_actor_suggestions([c1, c2], set(), min_score=0.85, limit=20)

    assert suggestions == []
    assert total == 1


def test_build_pair_above_min_score_included():
    c1 = _make_campaign("c1", "Campaign Alpha")
    c2 = _make_campaign("c2", "Campaign Beta")
    high = _make_result(sequence=0.90, timing=0.85, total=0.90)

    with patch(
        "app.intelligence.actor_suggestions.compute_weighted_similarity",
        return_value=high,
    ):
        suggestions, total = build_actor_suggestions([c1, c2], set(), min_score=0.85, limit=20)

    assert total == 1
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["similarity_score"] == 0.90
    assert s["campaign_a"]["id"] == "c1"
    assert s["campaign_b"]["id"] == "c2"
    assert "breakdown" in s
    assert "suggested_relationship_type" in s


def test_build_suggestion_fields_complete():
    c1 = _make_campaign("c1", "Alpha")
    c2 = _make_campaign("c2", "Beta")
    high = _make_result(total=0.90)

    with patch(
        "app.intelligence.actor_suggestions.compute_weighted_similarity",
        return_value=high,
    ):
        suggestions, _ = build_actor_suggestions([c1, c2], set(), min_score=0.85, limit=20)

    s = suggestions[0]
    assert set(s.keys()) == {
        "campaign_a",
        "campaign_b",
        "similarity_score",
        "breakdown",
        "suggested_relationship_type",
    }
    for key in ("id", "name", "status", "last_seen", "member_ip_count"):
        assert key in s["campaign_a"]
        assert key in s["campaign_b"]


# ---------------------------------------------------------------------------
# build_actor_suggestions — sort order and limit
# ---------------------------------------------------------------------------


def test_build_suggestions_sorted_descending():
    campaigns = [_make_campaign(f"c{i}") for i in range(3)]
    scores = [0.90, 0.95, 0.88]
    call_count = 0

    def mock_sim(a, b, **kwargs):
        nonlocal call_count
        s = scores[call_count % len(scores)]
        call_count += 1
        return _make_result(total=s)

    with patch(
        "app.intelligence.actor_suggestions.compute_weighted_similarity", side_effect=mock_sim
    ):
        suggestions, _ = build_actor_suggestions(campaigns, set(), min_score=0.0, limit=20)

    result_scores = [s["similarity_score"] for s in suggestions]
    assert result_scores == sorted(result_scores, reverse=True)


def test_build_limit_caps_results():
    campaigns = [_make_campaign(f"c{i}") for i in range(5)]
    high = _make_result(total=0.90)

    with patch(
        "app.intelligence.actor_suggestions.compute_weighted_similarity",
        return_value=high,
    ):
        suggestions, total = build_actor_suggestions(campaigns, set(), min_score=0.0, limit=3)

    assert len(suggestions) == 3
    # 5 campaigns → C(5,2) = 10 pairs evaluated
    assert total == 10


def test_build_limit_does_not_affect_total_pairs_evaluated():
    campaigns = [_make_campaign(f"c{i}") for i in range(4)]
    high = _make_result(total=0.90)

    with patch(
        "app.intelligence.actor_suggestions.compute_weighted_similarity",
        return_value=high,
    ):
        _, total_limit_1 = build_actor_suggestions(campaigns, set(), min_score=0.0, limit=1)
        _, total_limit_100 = build_actor_suggestions(campaigns, set(), min_score=0.0, limit=100)

    # C(4,2) = 6 regardless of limit
    assert total_limit_1 == 6
    assert total_limit_100 == 6


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_no_ai_imports_in_actor_suggestions():
    import inspect

    import app.intelligence.actor_suggestions as mod

    src = inspect.getsource(mod)
    assert "from app.ai" not in src
    assert "import app.ai" not in src
    assert "openai" not in src.lower()
    assert "anthropic" not in src.lower()


def test_no_db_imports_in_actor_suggestions():
    import inspect

    import app.intelligence.actor_suggestions as mod

    src = inspect.getsource(mod)
    assert "get_session" not in src
    assert "EventRepository" not in src
    assert "from app.db" not in src
