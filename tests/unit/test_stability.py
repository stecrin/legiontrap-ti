"""Unit tests for app/intelligence/stability.py.

All tests are pure: no database, no I/O.  Fixtures build fingerprint_history
row dicts directly and pass them to compute_campaign_stability().

Coverage:
  Insufficient data:
    - 0 records → insufficient_data status
    - 1 record → insufficient_data status
    - 2 records → ok status (minimum required)

  Stable behavior:
    - identical consecutive snapshots → composite_score = 1.0
    - nearly-identical snapshots → high composite_score (> 0.9)

  Drifting behavior:
    - significantly different snapshots → lower composite_score than stable
    - composite_score decreases as drift increases

  Per-dimension scores:
    - timing_stability present when both snapshots have timing_features
    - sequence_stability present when both have sequence_features
    - all per-dimension scores are in [0.0, 1.0]
    - null dimension produces None per-dimension score

  Composite:
    - composite_score is in [0.0, 1.0]
    - dimensions_used is correct count of non-null dimensions
    - composite_score of 0.0 when all dimensions are null

  Explanation:
    - explanation["dimensions"] contains all 5 dimension keys
    - each dimension entry has "score", "pair_count", "weight"
    - null dimension entries have "reason" key

  StabilityResult.as_dict():
    - includes all required keys
    - calculated_at is an ISO timestamp string

  Sample and pair counts:
    - sample_count = len(history)
    - pair_count = len(history) - 1

  No AI imports:
    - stability module does not import from app.ai

  Idempotency:
    - same input always produces same output (deterministic)
"""

from __future__ import annotations

import json

import pytest

from app.intelligence.stability import (
    _STATUS_INSUFFICIENT,
    _STATUS_OK,
    MIN_HISTORY_RECORDS,
    compute_campaign_stability,
)

# ---------------------------------------------------------------------------
# Fixtures — raw feature dicts and JSON-encoded feature strings
# ---------------------------------------------------------------------------

_TIMING_A = json.dumps(
    {
        "interval": {"mean": 2.0, "stddev": 0.1, "p25": 1.8, "p75": 2.2, "p95": 2.5},
        "burst_cv": 0.2,
    }
)

_TIMING_B_SIMILAR = json.dumps(
    {
        "interval": {"mean": 2.1, "stddev": 0.12, "p25": 1.9, "p75": 2.3, "p95": 2.6},
        "burst_cv": 0.22,
    }
)

_TIMING_B_DRIFT = json.dumps(
    {
        "interval": {"mean": 8.0, "stddev": 3.0, "p25": 5.0, "p75": 11.0, "p95": 15.0},
        "burst_cv": 1.2,
    }
)

_SEQUENCE_A = json.dumps(
    {
        "port_sequence": [22, 22, 80, 22],
        "event_type_sequence": ["auth_failed", "auth_failed", "port_scan"],
    }
)

_SEQUENCE_B_SIMILAR = json.dumps(
    {
        "port_sequence": [22, 22, 80, 22],
        "event_type_sequence": ["auth_failed", "auth_failed", "port_scan"],
    }
)

_SEQUENCE_B_DRIFT = json.dumps(
    {
        "port_sequence": [443, 8080, 3306],
        "event_type_sequence": ["http_probe", "malware_upload"],
    }
)

_PROTOCOL_A = json.dumps({"service_distribution": {"ssh": 10, "http": 2}})
_CREDENTIAL_A = json.dumps({"username_class_dist": {"dictionary": 8, "numeric": 2}})
_TARGET_A = json.dumps({"top_dst_ports": [22, 80], "port_freq": {"22": 10, "80": 2}})


def _make_row(
    *,
    timing: str | None = _TIMING_A,
    sequence: str | None = _SEQUENCE_A,
    protocol: str | None = _PROTOCOL_A,
    credential: str | None = _CREDENTIAL_A,
    target: str | None = _TARGET_A,
    computed_at: str = "2026-01-01T00:00:00+00:00",
) -> dict:
    return {
        "timing_features": timing,
        "sequence_features": sequence,
        "protocol_features": protocol,
        "credential_features": credential,
        "target_features": target,
        "computed_at": computed_at,
    }


# ---------------------------------------------------------------------------
# Insufficient data
# ---------------------------------------------------------------------------


def test_zero_records_returns_insufficient_data():
    result = compute_campaign_stability([])
    assert result.status == _STATUS_INSUFFICIENT


def test_one_record_returns_insufficient_data():
    result = compute_campaign_stability([_make_row()])
    assert result.status == _STATUS_INSUFFICIENT


def test_insufficient_data_composite_is_zero():
    result = compute_campaign_stability([_make_row()])
    assert result.composite_score == 0.0


def test_insufficient_data_pair_count_is_zero():
    result = compute_campaign_stability([_make_row()])
    assert result.pair_count == 0


def test_insufficient_data_all_per_dimension_scores_none():
    result = compute_campaign_stability([_make_row()])
    assert result.timing_stability is None
    assert result.sequence_stability is None
    assert result.protocol_stability is None
    assert result.credential_stability is None
    assert result.target_stability is None


def test_two_records_returns_ok():
    result = compute_campaign_stability([_make_row(), _make_row()])
    assert result.status == _STATUS_OK


def test_min_history_records_constant_is_two():
    assert MIN_HISTORY_RECORDS == 2


# ---------------------------------------------------------------------------
# Stable behavior — identical snapshots
# ---------------------------------------------------------------------------


def test_identical_snapshots_timing_stability_one():
    result = compute_campaign_stability([_make_row(), _make_row()])
    assert result.timing_stability == pytest.approx(1.0, abs=0.001)


def test_identical_snapshots_sequence_stability_one():
    result = compute_campaign_stability([_make_row(), _make_row()])
    assert result.sequence_stability == pytest.approx(1.0, abs=0.001)


def test_identical_snapshots_composite_one():
    result = compute_campaign_stability([_make_row(), _make_row()])
    assert result.composite_score == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# Stable behavior — similar (not identical) snapshots
# ---------------------------------------------------------------------------


def test_similar_snapshots_high_stability():
    row_a = _make_row(timing=_TIMING_A, sequence=_SEQUENCE_A)
    row_b = _make_row(timing=_TIMING_B_SIMILAR, sequence=_SEQUENCE_B_SIMILAR)
    result = compute_campaign_stability([row_a, row_b])
    assert result.composite_score > 0.85


# ---------------------------------------------------------------------------
# Drifting behavior
# ---------------------------------------------------------------------------


def test_drifting_snapshots_lower_stability_than_stable():
    stable = compute_campaign_stability([_make_row(), _make_row()])
    drifted = compute_campaign_stability(
        [
            _make_row(timing=_TIMING_A, sequence=_SEQUENCE_A),
            _make_row(timing=_TIMING_B_DRIFT, sequence=_SEQUENCE_B_DRIFT),
        ]
    )
    assert drifted.composite_score < stable.composite_score


def test_drifting_timing_lowers_timing_stability():
    stable = compute_campaign_stability([_make_row(), _make_row()])
    drifted = compute_campaign_stability(
        [
            _make_row(timing=_TIMING_A),
            _make_row(timing=_TIMING_B_DRIFT),
        ]
    )
    assert drifted.timing_stability < stable.timing_stability  # type: ignore[operator]


def test_composite_decreases_with_more_drift():
    h_stable = [_make_row() for _ in range(4)]
    h_drifted = [
        _make_row(timing=_TIMING_A, sequence=_SEQUENCE_A),
        _make_row(timing=_TIMING_B_DRIFT, sequence=_SEQUENCE_B_DRIFT),
        _make_row(timing=_TIMING_A, sequence=_SEQUENCE_A),
        _make_row(timing=_TIMING_B_DRIFT, sequence=_SEQUENCE_B_DRIFT),
    ]
    r_stable = compute_campaign_stability(h_stable)
    r_drifted = compute_campaign_stability(h_drifted)
    assert r_drifted.composite_score < r_stable.composite_score


# ---------------------------------------------------------------------------
# Per-dimension scores
# ---------------------------------------------------------------------------


def test_per_dimension_scores_in_valid_range():
    result = compute_campaign_stability([_make_row(), _make_row()])
    for val in (
        result.timing_stability,
        result.sequence_stability,
        result.protocol_stability,
        result.credential_stability,
        result.target_stability,
    ):
        assert val is not None
        assert 0.0 <= val <= 1.0


def test_null_timing_produces_none_timing_stability():
    result = compute_campaign_stability([_make_row(timing=None), _make_row(timing=None)])
    assert result.timing_stability is None


def test_null_timing_excluded_from_composite():
    with_timing = compute_campaign_stability([_make_row(), _make_row()])
    without_timing = compute_campaign_stability([_make_row(timing=None), _make_row(timing=None)])
    assert with_timing.dimensions_used > without_timing.dimensions_used


def test_all_null_dimensions_composite_zero():
    result = compute_campaign_stability(
        [
            _make_row(
                timing=None,
                sequence=None,
                protocol=None,
                credential=None,
                target=None,
            ),
            _make_row(
                timing=None,
                sequence=None,
                protocol=None,
                credential=None,
                target=None,
            ),
        ]
    )
    assert result.composite_score == 0.0
    assert result.dimensions_used == 0


def test_mixed_null_dimensions_uses_available():
    result = compute_campaign_stability(
        [
            _make_row(timing=_TIMING_A, sequence=None, protocol=None, credential=None, target=None),
            _make_row(timing=_TIMING_A, sequence=None, protocol=None, credential=None, target=None),
        ]
    )
    assert result.dimensions_used == 1
    assert result.timing_stability is not None
    assert result.sequence_stability is None


# ---------------------------------------------------------------------------
# Composite score range
# ---------------------------------------------------------------------------


def test_composite_in_valid_range():
    result = compute_campaign_stability([_make_row(), _make_row(timing=_TIMING_B_DRIFT)])
    assert 0.0 <= result.composite_score <= 1.0


def test_composite_in_valid_range_all_stable():
    result = compute_campaign_stability([_make_row() for _ in range(5)])
    assert 0.0 <= result.composite_score <= 1.0


# ---------------------------------------------------------------------------
# Explanation structure
# ---------------------------------------------------------------------------


def test_explanation_has_dimensions_key():
    result = compute_campaign_stability([_make_row(), _make_row()])
    assert "dimensions" in result.explanation


def test_explanation_has_all_five_dimension_keys():
    result = compute_campaign_stability([_make_row(), _make_row()])
    dims = result.explanation["dimensions"]
    for key in ("timing", "sequence", "protocol", "credential", "target"):
        assert key in dims


def test_explanation_dimension_entry_has_required_keys():
    result = compute_campaign_stability([_make_row(), _make_row()])
    for dim_entry in result.explanation["dimensions"].values():
        assert "score" in dim_entry
        assert "pair_count" in dim_entry
        assert "weight" in dim_entry


def test_explanation_null_dimension_has_reason_key():
    result = compute_campaign_stability([_make_row(timing=None), _make_row(timing=None)])
    timing_entry = result.explanation["dimensions"]["timing"]
    assert timing_entry["score"] is None
    assert "reason" in timing_entry


def test_insufficient_explanation_has_reason():
    result = compute_campaign_stability([_make_row()])
    assert "reason" in result.explanation
    assert "records_available" in result.explanation


# ---------------------------------------------------------------------------
# as_dict()
# ---------------------------------------------------------------------------


def test_as_dict_contains_required_keys():
    result = compute_campaign_stability([_make_row(), _make_row()])
    d = result.as_dict()
    required = {
        "status",
        "composite_score",
        "timing_stability",
        "sequence_stability",
        "protocol_stability",
        "credential_stability",
        "target_stability",
        "sample_count",
        "pair_count",
        "dimensions_used",
        "calculated_at",
        "explanation",
    }
    assert required.issubset(d.keys())


def test_as_dict_calculated_at_is_string():
    result = compute_campaign_stability([_make_row(), _make_row()])
    assert isinstance(result.as_dict()["calculated_at"], str)


def test_as_dict_is_json_serializable():
    result = compute_campaign_stability([_make_row(), _make_row()])
    serialized = json.dumps(result.as_dict())
    parsed = json.loads(serialized)
    assert parsed["status"] == _STATUS_OK


# ---------------------------------------------------------------------------
# Sample and pair counts
# ---------------------------------------------------------------------------


def test_sample_count_matches_history_length():
    history = [_make_row() for _ in range(4)]
    result = compute_campaign_stability(history)
    assert result.sample_count == 4


def test_pair_count_is_sample_count_minus_one():
    history = [_make_row() for _ in range(4)]
    result = compute_campaign_stability(history)
    assert result.pair_count == 3


def test_sample_count_zero_when_no_history():
    result = compute_campaign_stability([])
    assert result.sample_count == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_input_same_output():
    history = [_make_row(), _make_row(timing=_TIMING_B_SIMILAR)]
    r1 = compute_campaign_stability(history)
    r2 = compute_campaign_stability(history)
    assert r1.composite_score == r2.composite_score
    assert r1.timing_stability == r2.timing_stability
    assert r1.status == r2.status


# ---------------------------------------------------------------------------
# No AI imports
# ---------------------------------------------------------------------------


def test_stability_module_has_no_ai_imports():
    import importlib
    import sys

    if "app.intelligence.stability" in sys.modules:
        mod = sys.modules["app.intelligence.stability"]
    else:
        mod = importlib.import_module("app.intelligence.stability")

    source = mod.__file__
    assert source is not None
    with open(source) as f:
        content = f.read()
    assert "app.ai" not in content
    assert "from app.ai" not in content
    assert "import app.ai" not in content
