"""Unit tests for app/intelligence/fingerprint.py.

All tests use in-memory event dicts — no database, no HTTP.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.intelligence.constants import MIN_EVENTS_FOR_CLUSTERING
from app.intelligence.fingerprint import build_fingerprint, compute_confidence

_BASE_TS = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


def _make_event(offset_seconds: float = 0, dst_port: int = 22, source: str = "cowrie") -> dict:
    return {
        "ts": (_BASE_TS + timedelta(seconds=offset_seconds)).isoformat(),
        "dst_port": dst_port,
        "event_type": "auth_failed",
        "service": "ssh",
        "source": source,
        "raw_data": {},
    }


def _events(n: int) -> list[dict]:
    return [_make_event(i * 60) for i in range(n)]


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------


def test_confidence_zero_events():
    assert compute_confidence(0, 0, 6) == 0.0


def test_confidence_sparse_below_threshold():
    """All event counts below MIN_EVENTS_FOR_CLUSTERING must produce confidence < 0.20."""
    for n in range(1, MIN_EVENTS_FOR_CLUSTERING):
        c = compute_confidence(n, 3, 6)
        assert c < 0.20, f"Expected confidence < 0.20 for {n} events, got {c}"


def test_confidence_at_threshold_meets_lower_bound():
    """At exactly MIN_EVENTS_FOR_CLUSTERING, confidence must be >= 0.20."""
    c = compute_confidence(MIN_EVENTS_FOR_CLUSTERING, 0, 6)
    assert c >= 0.20


def test_confidence_grows_with_more_events():
    c10 = compute_confidence(10, 3, 6)
    c100 = compute_confidence(100, 3, 6)
    c500 = compute_confidence(500, 3, 6)
    assert c10 < c100 < c500


def test_confidence_grows_with_more_populated_categories():
    base = compute_confidence(50, 0, 6)
    full = compute_confidence(50, 6, 6)
    assert full > base


def test_confidence_capped_at_095():
    assert compute_confidence(10_000, 6, 6) <= 0.95


def test_confidence_is_non_negative():
    for n in range(0, 20):
        assert compute_confidence(n, 3, 6) >= 0.0


# ---------------------------------------------------------------------------
# build_fingerprint — return shape
# ---------------------------------------------------------------------------


def test_build_fingerprint_returns_expected_keys():
    result = build_fingerprint(_events(15))
    assert set(result.keys()) == {
        "event_count",
        "confidence",
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
        "tool_signals",
    }


def test_build_fingerprint_event_count_matches_input():
    events = _events(25)
    result = build_fingerprint(events)
    assert result["event_count"] == 25


# ---------------------------------------------------------------------------
# build_fingerprint — sparse fingerprints (< MIN_EVENTS_FOR_CLUSTERING)
# ---------------------------------------------------------------------------


def test_build_fingerprint_sparse_has_low_confidence():
    result = build_fingerprint(_events(MIN_EVENTS_FOR_CLUSTERING - 1))
    assert result["confidence"] < 0.20


def test_build_fingerprint_zero_events_confidence_zero():
    result = build_fingerprint([])
    assert result["confidence"] == 0.0


def test_build_fingerprint_sparse_still_stored():
    """Sparse fingerprints must be returned (for storage), not discarded."""
    result = build_fingerprint(_events(3))
    assert result is not None
    assert result["event_count"] == 3


# ---------------------------------------------------------------------------
# build_fingerprint — feature JSON strings
# ---------------------------------------------------------------------------


def test_build_fingerprint_feature_values_are_json_strings_or_none():
    feature_keys = [
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
        "tool_signals",
    ]
    result = build_fingerprint(_events(20))
    for key in feature_keys:
        val = result[key]
        assert val is None or isinstance(val, str), f"{key} should be str or None"
        if isinstance(val, str):
            parsed = json.loads(val)  # must be valid JSON
            assert isinstance(parsed, dict)


def test_build_fingerprint_timing_features_absent_below_2_events():
    """timing_features requires at least 2 events."""
    result = build_fingerprint(_events(1))
    assert result["timing_features"] is None


def test_build_fingerprint_credential_features_none_without_cred_data():
    """credential_features must be None when events have no credential data."""
    result = build_fingerprint(_events(20))
    assert result["credential_features"] is None


def test_build_fingerprint_with_cred_data_populates_credential_features():
    events = [
        {
            "ts": (_BASE_TS + timedelta(seconds=i * 60)).isoformat(),
            "dst_port": 22,
            "event_type": "auth_failed",
            "service": "ssh",
            "source": "cowrie",
            "raw_data": {"username": "admin", "password": "pass123"},
        }
        for i in range(15)
    ]
    result = build_fingerprint(events)
    assert result["credential_features"] is not None
    parsed = json.loads(result["credential_features"])
    assert "credential_count" in parsed
    assert parsed["credential_count"] == 15
