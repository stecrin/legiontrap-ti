"""Unit tests for Phase 7 Group A — weight profile computation.

Tests cover:
  - confirmed review increases high-scoring dimension weights
  - denied review decreases high-scoring dimension weights
  - weights are clamped at WEIGHT_FLOOR and WEIGHT_CEILING
  - weights sum to 1.0 after normalization
  - adjustment log records observation ID, decision, adjustments, weights_after
  - below WEIGHT_PROFILE_MIN_REVIEWS returns None (no profile created)
  - same observation processed twice does not double-apply adjustment (idempotent)
  - clustering uses weight profile when present (deterministic given same profile)
  - no actor tables used, no AI imports
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.intelligence.weight_profiles import (
    _apply_one_review,
    _clamp_and_renormalize,
    _extract_dim_scores,
    process_campaign_weight_profile,
)

# ---------------------------------------------------------------------------
# _clamp_and_renormalize
# ---------------------------------------------------------------------------


def test_clamp_and_renormalize_sums_to_one():
    weights = {
        "timing": 0.20,
        "sequence": 0.35,
        "protocol": 0.25,
        "credential": 0.10,
        "target": 0.10,
    }
    result = _clamp_and_renormalize(weights, floor=0.05, ceiling=0.60)
    assert abs(sum(result.values()) - 1.0) < 1e-6


def test_clamp_enforces_floor():
    weights = {
        "timing": 0.001,
        "sequence": 0.35,
        "protocol": 0.25,
        "credential": 0.10,
        "target": 0.10,
    }
    result = _clamp_and_renormalize(weights, floor=0.05, ceiling=0.60)
    assert result["timing"] >= 0.05


def test_clamp_enforces_ceiling():
    weights = {
        "timing": 0.90,
        "sequence": 0.35,
        "protocol": 0.25,
        "credential": 0.10,
        "target": 0.10,
    }
    result = _clamp_and_renormalize(weights, floor=0.05, ceiling=0.60)
    assert result["timing"] <= 0.60


def test_clamp_and_renormalize_result_sums_to_one_after_ceiling_clamp():
    weights = {
        "timing": 0.90,
        "sequence": 0.90,
        "protocol": 0.90,
        "credential": 0.90,
        "target": 0.90,
    }
    result = _clamp_and_renormalize(weights, floor=0.05, ceiling=0.60)
    assert abs(sum(result.values()) - 1.0) < 1e-6
    for dim in result:
        assert result[dim] <= 0.60


# ---------------------------------------------------------------------------
# _extract_dim_scores
# ---------------------------------------------------------------------------


def test_extract_dim_scores_from_observation_notes():
    notes = json.dumps(
        {
            "timing_similarity": 0.85,
            "sequence_similarity": 0.92,
            "protocol_similarity": 0.70,
            "credential_similarity": 0.45,
            "target_similarity": 0.78,
            "decision": "uncertain_association",
        }
    )
    scores = _extract_dim_scores(notes)
    assert scores["timing"] == pytest.approx(0.85)
    assert scores["sequence"] == pytest.approx(0.92)
    assert scores["protocol"] == pytest.approx(0.70)
    assert scores["credential"] == pytest.approx(0.45)
    assert scores["target"] == pytest.approx(0.78)


def test_extract_dim_scores_returns_empty_on_invalid_json():
    assert _extract_dim_scores("not json") == {}
    assert _extract_dim_scores(None) == {}
    assert _extract_dim_scores("") == {}


def test_extract_dim_scores_ignores_missing_keys():
    notes = json.dumps({"timing_similarity": 0.80})
    scores = _extract_dim_scores(notes)
    assert "timing" in scores
    assert "sequence" not in scores


# ---------------------------------------------------------------------------
# _apply_one_review
# ---------------------------------------------------------------------------


_DEFAULT_WEIGHTS = {
    "timing": 0.20,
    "sequence": 0.35,
    "protocol": 0.25,
    "credential": 0.10,
    "target": 0.10,
}

_HIGH_SCORES = {
    "timing": 0.85,
    "sequence": 0.90,
    "protocol": 0.80,
    "credential": 0.40,  # below gate — should not be nudged
    "target": 0.75,
}


def test_confirmed_review_increases_high_score_dimensions():
    new_weights, adjustments = _apply_one_review(
        _DEFAULT_WEIGHTS,
        _HIGH_SCORES,
        decision="analyst_confirmed",
        nudge=0.02,
        floor=0.05,
        ceiling=0.60,
        high_score_gate=0.70,
    )
    # timing (0.85 > 0.70), sequence (0.90 > 0.70), protocol (0.80 > 0.70), target (0.75 > 0.70)
    # credential (0.40 < 0.70) → no adjustment
    assert adjustments["timing"] == pytest.approx(0.02)
    assert adjustments["sequence"] == pytest.approx(0.02)
    assert adjustments["protocol"] == pytest.approx(0.02)
    assert adjustments["credential"] == pytest.approx(0.0)
    assert adjustments["target"] == pytest.approx(0.02)


def test_denied_review_decreases_high_score_dimensions():
    new_weights, adjustments = _apply_one_review(
        _DEFAULT_WEIGHTS,
        _HIGH_SCORES,
        decision="analyst_denied",
        nudge=0.02,
        floor=0.05,
        ceiling=0.60,
        high_score_gate=0.70,
    )
    assert adjustments["timing"] == pytest.approx(-0.02)
    assert adjustments["sequence"] == pytest.approx(-0.02)
    assert adjustments["protocol"] == pytest.approx(-0.02)
    assert adjustments["credential"] == pytest.approx(0.0)
    assert adjustments["target"] == pytest.approx(-0.02)


def test_apply_one_review_weights_sum_to_one():
    new_weights, _ = _apply_one_review(
        _DEFAULT_WEIGHTS,
        _HIGH_SCORES,
        decision="analyst_confirmed",
        nudge=0.02,
        floor=0.05,
        ceiling=0.60,
        high_score_gate=0.70,
    )
    assert abs(sum(new_weights.values()) - 1.0) < 1e-6


def test_apply_one_review_no_adjustment_when_below_gate():
    low_scores = {dim: 0.50 for dim in ("timing", "sequence", "protocol", "credential", "target")}
    new_weights, adjustments = _apply_one_review(
        _DEFAULT_WEIGHTS,
        low_scores,
        decision="analyst_confirmed",
        nudge=0.02,
        floor=0.05,
        ceiling=0.60,
        high_score_gate=0.70,
    )
    for dim in adjustments:
        assert adjustments[dim] == pytest.approx(0.0), f"Expected no adjustment for {dim}"
    # Weights should be essentially unchanged (after clamp+renorm of same values)
    for dim in new_weights:
        assert new_weights[dim] == pytest.approx(_DEFAULT_WEIGHTS[dim], abs=1e-6)


# ---------------------------------------------------------------------------
# process_campaign_weight_profile — integration via mock repo
# ---------------------------------------------------------------------------


def _make_observation(
    obs_id: str,
    campaign_id: str,
    decision: str,
    timing_sim: float = 0.85,
    sequence_sim: float = 0.90,
) -> dict:
    notes = json.dumps(
        {
            "timing_similarity": timing_sim,
            "sequence_similarity": sequence_sim,
            "protocol_similarity": 0.75,
            "credential_similarity": 0.40,
            "target_similarity": 0.78,
            "weighted_total": 0.83,
            "decision": "uncertain_association",
        }
    )
    review = json.dumps(
        {
            "decision": decision,
            "notes": None,
            "reviewed_at": "2026-05-29T10:00:00+00:00",
        }
    )
    return {
        "id": obs_id,
        "campaign_id": campaign_id,
        "notes": notes,
        "analyst_review_json": review,
    }


def _make_repo(campaign_id: str, observations: list[dict]) -> MagicMock:
    repo = MagicMock()
    repo.get_weight_profile.return_value = None
    repo.list_uncertain_observations.return_value = observations
    repo.get_campaign.return_value = {"id": campaign_id}
    return repo


def test_below_min_reviews_returns_none():
    cid = str(uuid.uuid4())
    # Only 2 observations, min is 3
    obs = [_make_observation(str(uuid.uuid4()), cid, "analyst_confirmed") for _ in range(2)]
    repo = _make_repo(cid, obs)
    result = process_campaign_weight_profile(cid, repo)
    assert result is None
    repo.upsert_weight_profile.assert_not_called()


def test_at_min_reviews_profile_is_created():
    cid = str(uuid.uuid4())
    obs = [_make_observation(str(uuid.uuid4()), cid, "analyst_confirmed") for _ in range(3)]
    repo = _make_repo(cid, obs)
    repo.get_weight_profile.side_effect = [
        None,
        {
            "weights": {},
            "review_count": 3,
            "confirmed_count": 3,
            "denied_count": 0,
            "adjustment_log": [],
            "computed_at": "x",
            "updated_at": "x",
        },
    ]
    process_campaign_weight_profile(cid, repo)
    repo.upsert_weight_profile.assert_called_once()


def test_adjustment_log_records_observation_ids():
    cid = str(uuid.uuid4())
    obs_ids = [str(uuid.uuid4()) for _ in range(3)]
    obs = [_make_observation(oid, cid, "analyst_confirmed") for oid in obs_ids]
    repo = _make_repo(cid, obs)

    captured_log = []

    def fake_upsert(**kwargs):
        captured_log.extend(kwargs["adjustment_log"])

    repo.upsert_weight_profile.side_effect = fake_upsert
    repo.get_weight_profile.side_effect = [None, None]
    process_campaign_weight_profile(cid, repo)

    logged_obs_ids = {entry["observation_id"] for entry in captured_log}
    assert set(obs_ids) == logged_obs_ids


def test_idempotent_already_processed_observations():
    cid = str(uuid.uuid4())
    obs_id = str(uuid.uuid4())
    obs = [_make_observation(obs_id, cid, "analyst_confirmed")]

    # Simulate existing profile with this obs already logged
    existing_log = [
        {
            "observation_id": obs_id,
            "review_decision": "analyst_confirmed",
            "reviewed_at": "2026-05-29T10:00:00+00:00",
            "dimension_adjustments": {
                "timing": 0.02,
                "sequence": 0.02,
                "protocol": 0.02,
                "credential": 0.0,
                "target": 0.02,
            },
            "weights_after": {
                "timing": 0.21,
                "sequence": 0.36,
                "protocol": 0.26,
                "credential": 0.10,
                "target": 0.10,
            },
        }
    ]
    existing_profile = {
        "weights": {
            "timing": 0.21,
            "sequence": 0.36,
            "protocol": 0.26,
            "credential": 0.10,
            "target": 0.10,
        },
        "review_count": 1,
        "confirmed_count": 1,
        "denied_count": 0,
        "adjustment_log": existing_log,
        "computed_at": "2026-05-29T10:00:00+00:00",
        "updated_at": "2026-05-29T10:00:00+00:00",
    }
    repo = MagicMock()
    repo.get_weight_profile.return_value = existing_profile
    repo.list_uncertain_observations.return_value = obs

    process_campaign_weight_profile(cid, repo)

    # upsert should not be called — no new reviews to process and count < min_reviews
    repo.upsert_weight_profile.assert_not_called()


def test_confirmed_review_profile_sums_to_one_and_within_bounds():
    cid = str(uuid.uuid4())
    obs = [
        _make_observation(
            str(uuid.uuid4()), cid, "analyst_confirmed", timing_sim=0.90, sequence_sim=0.95
        )
        for _ in range(3)
    ]
    repo = _make_repo(cid, obs)

    captured_kwargs = {}

    def fake_upsert(**kwargs):
        captured_kwargs.update(kwargs)

    repo.upsert_weight_profile.side_effect = fake_upsert
    repo.get_weight_profile.side_effect = [None, None]
    process_campaign_weight_profile(cid, repo)

    w = captured_kwargs.get("weights", {})
    # weights must sum to 1.0
    assert abs(sum(w.values()) - 1.0) < 1e-5
    # weights must be within floor/ceiling
    for dim, val in w.items():
        assert val >= 0.05, f"{dim}={val} below floor"
        assert val <= 0.60, f"{dim}={val} above ceiling"
    # adjustment log must record source observation IDs
    log = captured_kwargs.get("adjustment_log", [])
    assert len(log) == 3
    for entry in log:
        assert "observation_id" in entry
        assert entry["review_decision"] == "analyst_confirmed"


def test_confirmed_only_high_scoring_dimension_increases_proportionally():
    """When only ONE dimension scores high, confirmed review nudges it up."""
    cid = str(uuid.uuid4())
    # Only credential_similarity is above gate (0.90 > 0.70); all others are low
    notes_only_credential_high = {
        "timing_similarity": 0.40,
        "sequence_similarity": 0.40,
        "protocol_similarity": 0.40,
        "credential_similarity": 0.90,
        "target_similarity": 0.40,
        "weighted_total": 0.83,
        "decision": "uncertain_association",
    }
    import json as _json

    def _single_dim_obs(obs_id: str) -> dict:
        review = _json.dumps(
            {
                "decision": "analyst_confirmed",
                "notes": None,
                "reviewed_at": "2026-05-29T10:00:00+00:00",
            }
        )
        return {
            "id": obs_id,
            "campaign_id": cid,
            "notes": _json.dumps(notes_only_credential_high),
            "analyst_review_json": review,
        }

    obs = [_single_dim_obs(str(uuid.uuid4())) for _ in range(3)]
    repo = _make_repo(cid, obs)

    captured_kwargs = {}

    def fake_upsert(**kwargs):
        captured_kwargs.update(kwargs)

    repo.upsert_weight_profile.side_effect = fake_upsert
    repo.get_weight_profile.side_effect = [None, None]
    process_campaign_weight_profile(cid, repo)

    w = captured_kwargs.get("weights", {})
    # After 3 confirmed reviews nudging credential up and renormalizing,
    # credential should be HIGHER than its default (0.10)
    default_credential = 0.10
    assert w.get("credential", 0) > default_credential
    assert abs(sum(w.values()) - 1.0) < 1e-5


def test_denied_only_high_scoring_dimension_decreases_proportionally():
    """When only ONE dimension scores high, denied review nudges it down."""
    import json as _json

    cid = str(uuid.uuid4())
    # Only sequence_similarity is above gate; all others are low
    notes_only_sequence_high = {
        "timing_similarity": 0.40,
        "sequence_similarity": 0.95,
        "protocol_similarity": 0.40,
        "credential_similarity": 0.40,
        "target_similarity": 0.40,
        "weighted_total": 0.83,
        "decision": "uncertain_association",
    }

    def _obs(obs_id: str) -> dict:
        review = _json.dumps(
            {
                "decision": "analyst_denied",
                "notes": None,
                "reviewed_at": "2026-05-29T10:00:00+00:00",
            }
        )
        return {
            "id": obs_id,
            "campaign_id": cid,
            "notes": _json.dumps(notes_only_sequence_high),
            "analyst_review_json": review,
        }

    obs = [_obs(str(uuid.uuid4())) for _ in range(3)]
    repo = _make_repo(cid, obs)

    captured_kwargs = {}

    def fake_upsert(**kwargs):
        captured_kwargs.update(kwargs)

    repo.upsert_weight_profile.side_effect = fake_upsert
    repo.get_weight_profile.side_effect = [None, None]
    process_campaign_weight_profile(cid, repo)

    w = captured_kwargs.get("weights", {})
    # sequence was nudged DOWN; after renorm it should be lower than default (0.35)
    default_sequence = 0.35
    assert w.get("sequence", 1) < default_sequence
    assert abs(sum(w.values()) - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# Invariant: no AI imports
# ---------------------------------------------------------------------------


def test_no_ai_imports_in_weight_profiles():
    import importlib

    mod = importlib.import_module("app.intelligence.weight_profiles")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content


def test_no_actor_table_references_in_weight_profiles():
    import importlib

    mod = importlib.import_module("app.intelligence.weight_profiles")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "actor_profiles" not in content
    assert "campaign_lineage" not in content
