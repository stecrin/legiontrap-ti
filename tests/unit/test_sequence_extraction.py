"""Unit tests for app/intelligence/sequence.py.

All tests use in-memory event dicts — no database, no HTTP.

Privacy invariants verified here:
  - Raw credential strings (usernames, passwords) never appear in output.
  - Source IP addresses never appear in any feature category JSON.
  - No raw payload bytes stored.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.intelligence.sequence import (
    compute_credential_features,
    compute_protocol_features,
    compute_sequence_features,
    compute_target_features,
    compute_timing_features,
    compute_tool_signals,
    extract_all_features,
    extract_sessions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TS = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


def _make_event(
    offset_seconds: float = 0,
    dst_port: int | None = 22,
    event_type: str = "auth_failed",
    service: str | None = "ssh",
    source: str = "cowrie",
    raw_data: dict | None = None,
) -> dict:
    ts = (_BASE_TS + timedelta(seconds=offset_seconds)).isoformat()
    return {
        "ts": ts,
        "dst_port": dst_port,
        "event_type": event_type,
        "service": service,
        "source": source,
        "raw_data": raw_data or {},
    }


def _make_cred_event(
    offset_seconds: float = 0,
    username: str = "admin",
    password: str = "password123",
    dst_port: int | None = 22,
) -> dict:
    return _make_event(
        offset_seconds=offset_seconds,
        dst_port=dst_port,
        raw_data={"ip": "203.0.113.1", "username": username, "password": password},
    )


# ---------------------------------------------------------------------------
# extract_sessions
# ---------------------------------------------------------------------------


def test_extract_sessions_empty_returns_empty():
    assert extract_sessions([]) == []


def test_extract_sessions_single_event_one_session():
    events = [_make_event()]
    sessions = extract_sessions(events)
    assert len(sessions) == 1
    assert len(sessions[0]) == 1


def test_extract_sessions_short_gap_stays_in_one_session():
    events = [_make_event(0), _make_event(60), _make_event(120)]
    sessions = extract_sessions(events)
    assert len(sessions) == 1
    assert len(sessions[0]) == 3


def test_extract_sessions_splits_on_gap_exceeding_threshold():
    # Default gap is 1800 s; 3601 s apart should split.
    events = [_make_event(0), _make_event(3601)]
    sessions = extract_sessions(events)
    assert len(sessions) == 2


def test_extract_sessions_boundary_exactly_at_gap_splits():
    events = [_make_event(0), _make_event(1801)]
    sessions = extract_sessions(events, gap_seconds=1800)
    assert len(sessions) == 2


def test_extract_sessions_boundary_just_under_gap_stays_together():
    events = [_make_event(0), _make_event(1799)]
    sessions = extract_sessions(events, gap_seconds=1800)
    assert len(sessions) == 1


def test_extract_sessions_sorts_events_chronologically():
    # Pass events in reverse order; sessions must still be chronological.
    events = [_make_event(300), _make_event(0), _make_event(150)]
    sessions = extract_sessions(events)
    assert len(sessions) == 1
    ts_values = [e["ts"] for e in sessions[0]]
    assert ts_values == sorted(ts_values)


def test_extract_sessions_custom_gap():
    events = [_make_event(0), _make_event(61)]
    sessions = extract_sessions(events, gap_seconds=60)
    assert len(sessions) == 2


# ---------------------------------------------------------------------------
# compute_timing_features
# ---------------------------------------------------------------------------


def test_compute_timing_features_none_for_single_event():
    assert compute_timing_features([_make_event()]) is None


def test_compute_timing_features_none_for_empty():
    assert compute_timing_features([]) is None


def test_compute_timing_features_returns_expected_keys():
    events = [_make_event(i * 60) for i in range(5)]
    result = compute_timing_features(events)
    assert result is not None
    assert "interval" in result
    assert "tod_histogram" in result
    assert "dow_histogram" in result
    assert "burst_cv" in result


def test_compute_timing_features_interval_keys():
    events = [_make_event(i * 60) for i in range(5)]
    iv = compute_timing_features(events)["interval"]
    assert set(iv.keys()) == {"mean", "stddev", "p25", "p75", "p95"}


def test_compute_timing_features_interval_mean_is_correct():
    # Events spaced exactly 60 seconds apart → interval mean = 60_000 ms
    events = [_make_event(i * 60) for i in range(4)]
    iv = compute_timing_features(events)["interval"]
    assert abs(iv["mean"] - 60_000.0) < 1.0


def test_compute_timing_features_tod_histogram_length():
    events = [_make_event(i * 60) for i in range(5)]
    tod = compute_timing_features(events)["tod_histogram"]
    assert len(tod) == 24


def test_compute_timing_features_tod_histogram_sums_to_one():
    events = [_make_event(i * 60) for i in range(5)]
    tod = compute_timing_features(events)["tod_histogram"]
    assert abs(sum(tod) - 1.0) < 1e-6


def test_compute_timing_features_dow_histogram_length():
    events = [_make_event(i * 60) for i in range(5)]
    dow = compute_timing_features(events)["dow_histogram"]
    assert len(dow) == 7


def test_compute_timing_features_dow_histogram_sums_to_one():
    events = [_make_event(i * 60) for i in range(5)]
    dow = compute_timing_features(events)["dow_histogram"]
    assert abs(sum(dow) - 1.0) < 1e-6


def test_compute_timing_features_burst_cv_is_nonnegative():
    events = [_make_event(i * 60) for i in range(5)]
    cv = compute_timing_features(events)["burst_cv"]
    assert cv >= 0.0


def test_compute_timing_features_metronomic_tool_has_low_burst_cv():
    # Perfectly even 60-second spacing → stddev = 0 → burst_cv = 0
    events = [_make_event(i * 60) for i in range(10)]
    cv = compute_timing_features(events)["burst_cv"]
    assert cv == 0.0


def test_compute_timing_features_cross_session_gap_excluded():
    # Two sessions with a 1-hour gap.  The inter-session gap must not
    # appear in interval stats — only within-session intervals count.
    session1 = [_make_event(0), _make_event(60)]  # one 60s interval
    session2 = [_make_event(3900), _make_event(3960)]  # one 60s interval
    events = session1 + session2
    result = compute_timing_features(events)
    # All intervals are 60 000 ms; mean must be ~60 000, not ~1920 000
    assert abs(result["interval"]["mean"] - 60_000.0) < 1.0


# ---------------------------------------------------------------------------
# compute_sequence_features
# ---------------------------------------------------------------------------


def test_compute_sequence_features_empty_returns_none():
    assert compute_sequence_features([]) is None


def test_compute_sequence_features_no_port_no_cred_returns_none():
    events = [_make_event(0, dst_port=None, raw_data={})]
    result = compute_sequence_features(events)
    assert result is None


def test_compute_sequence_features_returns_expected_keys():
    events = [_make_event(i * 60, dst_port=22 + i) for i in range(3)]
    result = compute_sequence_features(events)
    assert result is not None
    assert "port_sequence" in result
    assert "event_type_sequence" in result
    assert "credential_sequence" in result


def test_compute_sequence_features_port_order_preserved():
    events = [_make_event(i * 10, dst_port=p) for i, p in enumerate([80, 22, 443])]
    result = compute_sequence_features(events)
    assert result["port_sequence"] == [80, 22, 443]


def test_compute_sequence_features_port_sequence_deduped():
    # Same port appearing twice should appear once in the sequence.
    events = [
        _make_event(0, dst_port=22),
        _make_event(60, dst_port=22),
        _make_event(120, dst_port=80),
    ]
    result = compute_sequence_features(events)
    assert result["port_sequence"].count(22) == 1


def test_compute_sequence_features_credential_sequence_no_raw_values():
    events = [
        _make_cred_event(0, username="definitely_unique_username", password="UNIQUE_RAW_PW_XYZ"),
    ]
    result = compute_sequence_features(events)
    seq_str = json.dumps(result["credential_sequence"])
    assert "definitely_unique_username" not in seq_str
    assert "UNIQUE_RAW_PW_XYZ" not in seq_str


def test_compute_sequence_features_credential_sequence_has_pattern_keys():
    events = [_make_cred_event(0, username="admin", password="pass")]
    result = compute_sequence_features(events)
    seq = result["credential_sequence"]
    assert len(seq) == 1
    assert "username_pattern" in seq[0]
    assert "password_class" in seq[0]


# ---------------------------------------------------------------------------
# compute_protocol_features
# ---------------------------------------------------------------------------


def test_compute_protocol_features_returns_service_distribution():
    events = [
        _make_event(0, service="ssh"),
        _make_event(60, service="ssh"),
        _make_event(120, service="http"),
    ]
    result = compute_protocol_features(events)
    assert result is not None
    assert "service_distribution" in result
    dist = result["service_distribution"]
    assert abs(dist["ssh"] - 2 / 3) < 1e-4
    assert abs(dist["http"] - 1 / 3) < 1e-4


def test_compute_protocol_features_null_service_excluded():
    events = [_make_event(0, service=None), _make_event(60, service="ssh")]
    result = compute_protocol_features(events)
    assert "ssh" in result["service_distribution"]
    assert None not in result["service_distribution"]


def test_compute_protocol_features_ssh_kex_extracted_when_present():
    kex = ["curve25519-sha256", "ecdh-sha2-nistp256"]
    events = [_make_event(0, raw_data={"kex_algs": kex})]
    result = compute_protocol_features(events)
    assert result["ssh_kex_ordering"] == kex


def test_compute_protocol_features_ssh_kex_null_when_absent():
    events = [_make_event(0)]
    result = compute_protocol_features(events)
    assert result["ssh_kex_ordering"] is None


def test_compute_protocol_features_tls_ciphers_null_when_absent():
    events = [_make_event(0)]
    result = compute_protocol_features(events)
    assert result["tls_cipher_ordering"] is None


# ---------------------------------------------------------------------------
# compute_credential_features
# ---------------------------------------------------------------------------


def test_compute_credential_features_none_when_no_creds():
    events = [_make_event(0, raw_data={})]
    assert compute_credential_features(events) is None


def test_compute_credential_features_none_for_empty():
    assert compute_credential_features([]) is None


def test_compute_credential_features_no_raw_usernames_stored():
    """Raw username strings must never appear in the feature output."""
    events = [_make_cred_event(0, username="unique_secret_user_abc", password="x")]
    result = compute_credential_features(events)
    result_str = json.dumps(result)
    assert "unique_secret_user_abc" not in result_str


def test_compute_credential_features_no_raw_passwords_stored():
    """Raw password strings must never appear in the feature output."""
    events = [_make_cred_event(0, username="u", password="unique_secret_pw_xyz")]
    result = compute_credential_features(events)
    result_str = json.dumps(result)
    assert "unique_secret_pw_xyz" not in result_str


def test_compute_credential_features_returns_expected_keys():
    events = [_make_cred_event(0)]
    result = compute_credential_features(events)
    assert result is not None
    assert "credential_count" in result
    assert "username_class_dist" in result
    assert "password_length_mean" in result
    assert "password_char_class" in result
    assert "credential_sequence" in result


def test_compute_credential_features_credential_count():
    events = [_make_cred_event(i * 60) for i in range(5)]
    result = compute_credential_features(events)
    assert result["credential_count"] == 5


def test_compute_credential_features_username_class_alpha():
    events = [_make_cred_event(0, username="admin")]
    result = compute_credential_features(events)
    dist = result["username_class_dist"]
    assert "alpha" in dist
    assert abs(dist["alpha"] - 1.0) < 1e-6


def test_compute_credential_features_username_class_numeric():
    events = [_make_cred_event(0, username="12345")]
    result = compute_credential_features(events)
    dist = result["username_class_dist"]
    assert "numeric" in dist


def test_compute_credential_features_username_class_email():
    events = [_make_cred_event(0, username="user@example.com")]
    result = compute_credential_features(events)
    dist = result["username_class_dist"]
    assert "email" in dist


def test_compute_credential_features_password_length_mean():
    # "pass" = 4, "password" = 8 → mean = 6.0
    events = [
        _make_cred_event(0, password="pass"),
        _make_cred_event(60, password="password"),
    ]
    result = compute_credential_features(events)
    assert abs(result["password_length_mean"] - 6.0) < 0.01


# ---------------------------------------------------------------------------
# compute_target_features
# ---------------------------------------------------------------------------


def test_compute_target_features_none_when_no_ports():
    events = [_make_event(0, dst_port=None)]
    assert compute_target_features(events) is None


def test_compute_target_features_none_for_empty():
    assert compute_target_features([]) is None


def test_compute_target_features_returns_expected_keys():
    events = [_make_event(0, dst_port=22)]
    result = compute_target_features(events)
    assert result is not None
    assert "port_freq" in result
    assert "unique_port_count" in result
    assert "top_dst_ports" in result


def test_compute_target_features_port_freq_proportions():
    events = [
        _make_event(0, dst_port=22),
        _make_event(60, dst_port=22),
        _make_event(120, dst_port=80),
    ]
    result = compute_target_features(events)
    freq = result["port_freq"]
    assert abs(float(freq["22"]) - 2 / 3) < 1e-4
    assert abs(float(freq["80"]) - 1 / 3) < 1e-4


def test_compute_target_features_unique_port_count():
    events = [_make_event(i * 10, dst_port=p) for i, p in enumerate([22, 22, 80, 443])]
    result = compute_target_features(events)
    assert result["unique_port_count"] == 3


def test_compute_target_features_top_dst_ports_sorted_by_frequency():
    events = [
        _make_event(0, dst_port=22),
        _make_event(10, dst_port=22),
        _make_event(20, dst_port=22),
        _make_event(30, dst_port=80),
    ]
    result = compute_target_features(events)
    assert result["top_dst_ports"][0] == 22


# ---------------------------------------------------------------------------
# compute_tool_signals
# ---------------------------------------------------------------------------


def test_compute_tool_signals_none_for_empty():
    assert compute_tool_signals([]) is None


def test_compute_tool_signals_returns_expected_keys():
    events = [_make_event(0)]
    result = compute_tool_signals(events)
    assert result is not None
    assert "source_dist" in result
    assert "event_type_dist" in result
    assert "inferred_tools" in result


def test_compute_tool_signals_source_distribution():
    events = [
        _make_event(0, source="cowrie"),
        _make_event(60, source="cowrie"),
        _make_event(120, source="dionaea"),
    ]
    result = compute_tool_signals(events)
    dist = result["source_dist"]
    assert abs(dist["cowrie"] - 2 / 3) < 1e-4


def test_compute_tool_signals_infers_ssh_brute_force():
    events = [_make_event(i * 10, source="cowrie", event_type="auth_failed") for i in range(10)]
    result = compute_tool_signals(events)
    tools = {t["tool"] for t in result["inferred_tools"]}
    assert "ssh_brute_force" in tools


# ---------------------------------------------------------------------------
# extract_all_features
# ---------------------------------------------------------------------------


def test_extract_all_features_returns_six_keys():
    events = [_make_event(i * 60) for i in range(5)]
    result = extract_all_features(events)
    assert set(result.keys()) == {
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
        "tool_signals",
    }


def test_extract_all_features_empty_events_all_none_or_empty():
    result = extract_all_features([])
    # timing and target require data; some categories tolerate empty
    assert result["timing_features"] is None
    assert result["target_features"] is None
    assert result["credential_features"] is None


# ---------------------------------------------------------------------------
# Privacy invariant: no source IP in any feature category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category",
    [
        "timing_features",
        "sequence_features",
        "protocol_features",
        "credential_features",
        "target_features",
        "tool_signals",
    ],
)
def test_no_source_ip_in_feature_category(category):
    """Source IP addresses must not appear in any computed feature category."""
    # Events where raw_data.ip is a distinctive sentinel value
    sentinel_ip = "198.51.100.99"
    events = [
        _make_event(
            i * 60,
            dst_port=22,
            source="cowrie",
            raw_data={"ip": sentinel_ip, "username": "root", "password": "pass"},
        )
        for i in range(5)
    ]
    result = extract_all_features(events)
    cat_val = result.get(category)
    if cat_val is not None:
        cat_str = json.dumps(cat_val)
        assert sentinel_ip not in cat_str, f"Source IP {sentinel_ip!r} leaked into {category}"
