"""Unit tests for app/intelligence/similarity.py.

All tests use in-memory dicts only — no database, no HTTP.
"""

from __future__ import annotations

import json

import pytest

from app.intelligence.similarity import (
    SimilarityResult,
    _cv_sim,
    _dict_jaccard,
    _histogram_sim,
    _jaccard,
    _jsd,
    _levenshtein,
    _normalized_edit_sim,
    _stat_sim,
    compute_weighted_similarity,
    credential_similarity,
    protocol_similarity,
    sequence_similarity,
    target_similarity,
    timing_similarity,
)

# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------


def test_stat_sim_identical():
    assert _stat_sim(100.0, 100.0) == pytest.approx(1.0)


def test_stat_sim_both_zero():
    assert _stat_sim(0.0, 0.0) == pytest.approx(1.0)


def test_stat_sim_one_zero():
    # 1 - 100 / (100 + 1) ≈ 0.0099
    result = _stat_sim(0.0, 100.0)
    assert result < 0.02


def test_stat_sim_range():
    assert 0.0 <= _stat_sim(1.0, 10.0) <= 1.0


def test_cv_sim_identical():
    assert _cv_sim(0.5, 0.5) == pytest.approx(1.0)


def test_cv_sim_difference_above_one_clamps():
    assert _cv_sim(0.0, 2.0) == pytest.approx(0.0)


def test_levenshtein_empty():
    assert _levenshtein([], []) == 0
    assert _levenshtein([1, 2], []) == 2
    assert _levenshtein([], [1, 2]) == 2


def test_levenshtein_identical():
    assert _levenshtein([22, 80, 443], [22, 80, 443]) == 0


def test_levenshtein_one_substitution():
    assert _levenshtein([22, 80], [22, 443]) == 1


def test_normalized_edit_sim_both_empty():
    assert _normalized_edit_sim([], []) == pytest.approx(1.0)


def test_normalized_edit_sim_identical():
    assert _normalized_edit_sim([22, 80], [22, 80]) == pytest.approx(1.0)


def test_normalized_edit_sim_fully_different():
    # [1] vs [2]: edit distance 1, max_len 1 → 0.0
    assert _normalized_edit_sim([1], [2]) == pytest.approx(0.0)


def test_normalized_edit_sim_partial():
    result = _normalized_edit_sim([22, 80, 443], [22, 80, 22])
    assert 0.0 < result < 1.0


def test_jaccard_both_empty():
    assert _jaccard(set(), set()) == pytest.approx(1.0)


def test_jaccard_identical():
    s = {22, 80, 443}
    assert _jaccard(s, s) == pytest.approx(1.0)


def test_jaccard_disjoint():
    assert _jaccard({1, 2}, {3, 4}) == pytest.approx(0.0)


def test_jaccard_partial_overlap():
    result = _jaccard({1, 2, 3}, {2, 3, 4})
    # |{2,3}| / |{1,2,3,4}| = 2/4 = 0.5
    assert result == pytest.approx(0.5)


def test_jsd_identical_distributions():
    p = [0.5, 0.5]
    assert _jsd(p, p) == pytest.approx(0.0)


def test_jsd_maximally_different():
    p = [1.0, 0.0]
    q = [0.0, 1.0]
    # JSD(p||q) = 1.0 for log base 2
    assert _jsd(p, q) == pytest.approx(1.0)


def test_jsd_length_mismatch_returns_one():
    assert _jsd([0.5, 0.5], [0.33, 0.33, 0.34]) == pytest.approx(1.0)


def test_histogram_sim_none_input():
    assert _histogram_sim(None, [0.5, 0.5]) is None
    assert _histogram_sim([0.5, 0.5], None) is None


def test_histogram_sim_identical():
    p = [1.0 / 24] * 24
    result = _histogram_sim(p, p)
    assert result == pytest.approx(1.0)


def test_dict_jaccard_empty():
    assert _dict_jaccard({}, {}) == pytest.approx(1.0)


def test_dict_jaccard_partial():
    a = {"ssh": 0.8, "telnet": 0.2}
    b = {"ssh": 0.6, "ftp": 0.4}
    # keys: {ssh} / {ssh, telnet, ftp} = 1/3
    assert _dict_jaccard(a, b) == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# timing_similarity
# ---------------------------------------------------------------------------


def _timing_dict():
    return {
        "interval": {"mean": 1000.0, "stddev": 50.0, "p25": 800.0, "p75": 1200.0, "p95": 1400.0},
        "tod_histogram": [1.0 / 24] * 24,
        "dow_histogram": [1.0 / 7] * 7,
        "burst_cv": 0.05,
    }


def test_timing_similarity_identical():
    t = _timing_dict()
    assert timing_similarity(t, t) == pytest.approx(1.0, abs=1e-4)


def test_timing_similarity_null_returns_none():
    assert timing_similarity(None, _timing_dict()) is None
    assert timing_similarity(_timing_dict(), None) is None


def test_timing_similarity_both_null_returns_none():
    assert timing_similarity(None, None) is None


def test_timing_similarity_different_intervals_lower_score():
    t1 = _timing_dict()
    t2 = {
        **_timing_dict(),
        "interval": {"mean": 5000.0, "stddev": 200.0, "p25": 4000.0, "p75": 6000.0, "p95": 7000.0},
    }
    result = timing_similarity(t1, t2)
    assert result is not None
    assert result < 0.9


def test_timing_similarity_in_range():
    t1 = _timing_dict()
    t2 = {**_timing_dict(), "burst_cv": 1.0}
    result = timing_similarity(t1, t2)
    assert result is not None
    assert 0.0 <= result <= 1.0


def test_timing_similarity_empty_dicts_returns_zero():
    assert timing_similarity({}, {}) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# sequence_similarity
# ---------------------------------------------------------------------------


def test_sequence_similarity_identical():
    s = {
        "port_sequence": [22, 80, 443],
        "event_type_sequence": ["auth_failed", "auth_failed"],
        "credential_sequence": [{"username_pattern": "alpha", "password_class": "alphanum"}],
    }
    assert sequence_similarity(s, s) == pytest.approx(1.0)


def test_sequence_similarity_null_returns_none():
    s = {"port_sequence": [22]}
    assert sequence_similarity(None, s) is None


def test_sequence_similarity_identical_ports_only():
    s = {"port_sequence": [22, 80]}
    assert sequence_similarity(s, s) == pytest.approx(1.0)


def test_sequence_similarity_disjoint_ports():
    s1 = {"port_sequence": [22]}
    s2 = {"port_sequence": [443]}
    result = sequence_similarity(s1, s2)
    assert result is not None
    assert result < 0.5


def test_sequence_similarity_empty_sequences_identical():
    s1 = {"port_sequence": [], "event_type_sequence": [], "credential_sequence": []}
    s2 = {"port_sequence": [], "event_type_sequence": [], "credential_sequence": []}
    # All sub-components skip when empty — scores list empty → 0.0
    assert sequence_similarity(s1, s2) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# protocol_similarity
# ---------------------------------------------------------------------------


def test_protocol_similarity_identical():
    p = {
        "service_distribution": {"ssh": 1.0},
        "ssh_kex_ordering": ["diffie-hellman-group14-sha256", "ecdh-sha2-nistp256"],
        "tls_cipher_ordering": None,
    }
    assert protocol_similarity(p, p) == pytest.approx(1.0)


def test_protocol_similarity_null_returns_none():
    p = {"service_distribution": {"ssh": 1.0}}
    assert protocol_similarity(None, p) is None


def test_protocol_similarity_service_jaccard():
    p1 = {"service_distribution": {"ssh": 0.8, "telnet": 0.2}}
    p2 = {"service_distribution": {"ssh": 0.6, "ftp": 0.4}}
    result = protocol_similarity(p1, p2)
    assert result is not None
    # Jaccard of {ssh,telnet} vs {ssh,ftp} = 1/3
    assert result == pytest.approx(1 / 3, abs=0.01)


def test_protocol_similarity_kex_ordering():
    # 3-alg list with first two swapped: edit_distance = 2, max_len = 3 → sim = 1/3
    algs = ["ecdh-sha2-nistp256", "diffie-hellman-group14-sha256", "curve25519-sha256"]
    algs_swapped = ["diffie-hellman-group14-sha256", "ecdh-sha2-nistp256", "curve25519-sha256"]
    p1 = {"service_distribution": {"ssh": 1.0}, "ssh_kex_ordering": algs}
    p2 = {"service_distribution": {"ssh": 1.0}, "ssh_kex_ordering": algs_swapped}
    result = protocol_similarity(p1, p2)
    assert result is not None
    # service Jaccard = 1.0; kex edit sim < 1.0 → average in (0, 1)
    assert 0.0 < result < 1.0


# ---------------------------------------------------------------------------
# credential_similarity
# ---------------------------------------------------------------------------


def test_credential_similarity_identical():
    c = {
        "username_class_dist": {"alpha": 0.8, "alphanum": 0.2},
        "password_char_class": {"has_upper_ratio": 0.1, "has_digit_ratio": 0.9},
        "credential_sequence": [{"username_pattern": "alpha", "password_class": "alphanum"}],
    }
    assert credential_similarity(c, c) == pytest.approx(1.0)


def test_credential_similarity_null_returns_none():
    c = {"username_class_dist": {"alpha": 1.0}}
    assert credential_similarity(None, c) is None


def test_credential_similarity_class_jaccard():
    c1 = {"username_class_dist": {"alpha": 0.5, "numeric": 0.5}}
    c2 = {"username_class_dist": {"alpha": 0.8, "email": 0.2}}
    result = credential_similarity(c1, c2)
    # keys: {alpha} / {alpha, numeric, email} = 1/3
    assert result is not None
    assert result == pytest.approx(1 / 3, abs=0.01)


# ---------------------------------------------------------------------------
# target_similarity
# ---------------------------------------------------------------------------


def test_target_similarity_identical():
    t = {
        "port_freq": {"22": 0.8, "80": 0.2},
        "top_dst_ports": [22, 80],
    }
    assert target_similarity(t, t) == pytest.approx(1.0)


def test_target_similarity_null_returns_none():
    t = {"port_freq": {"22": 1.0}}
    assert target_similarity(None, t) is None


def test_target_similarity_disjoint_ports():
    t1 = {"port_freq": {"22": 1.0}, "top_dst_ports": [22]}
    t2 = {"port_freq": {"443": 1.0}, "top_dst_ports": [443]}
    result = target_similarity(t1, t2)
    assert result is not None
    assert result == pytest.approx(0.0)


def test_target_similarity_partial_overlap():
    t1 = {"port_freq": {"22": 0.5, "80": 0.5}, "top_dst_ports": [22, 80]}
    t2 = {"port_freq": {"22": 0.7, "443": 0.3}, "top_dst_ports": [22, 443]}
    result = target_similarity(t1, t2)
    assert result is not None
    assert 0.0 < result < 1.0


# ---------------------------------------------------------------------------
# compute_weighted_similarity
# ---------------------------------------------------------------------------


def _make_fp(
    timing=None,
    sequence=None,
    protocol=None,
    credential=None,
    target=None,
):
    """Build a minimal fingerprint dict with JSON-encoded features."""

    def _enc(d):
        return json.dumps(d, separators=(",", ":")) if d is not None else None

    return {
        "timing_features": _enc(timing),
        "sequence_features": _enc(sequence),
        "protocol_features": _enc(protocol),
        "credential_features": _enc(credential),
        "target_features": _enc(target),
    }


_FULL_TIMING = {
    "interval": {"mean": 1000.0, "stddev": 10.0, "p25": 950.0, "p75": 1050.0, "p95": 1100.0},
    "tod_histogram": [1 / 24] * 24,
    "dow_histogram": [1 / 7] * 7,
    "burst_cv": 0.01,
}
_FULL_SEQUENCE = {
    "port_sequence": [22, 80, 443],
    "event_type_sequence": ["auth_failed"] * 10,
    "credential_sequence": [{"username_pattern": "alpha", "password_class": "alphanum"}],
}
_FULL_TARGET = {
    "port_freq": {"22": 0.9, "80": 0.1},
    "top_dst_ports": [22, 80],
}


def test_weighted_similarity_identical_full_fp():
    fp = _make_fp(timing=_FULL_TIMING, sequence=_FULL_SEQUENCE, target=_FULL_TARGET)
    result = compute_weighted_similarity(fp, fp)
    assert isinstance(result, SimilarityResult)
    assert result.weighted_total == pytest.approx(1.0, abs=1e-4)


def test_weighted_similarity_all_null_returns_zero():
    fp = _make_fp()
    result = compute_weighted_similarity(fp, fp)
    assert result.weighted_total == pytest.approx(0.0)
    assert result.dimensions_used == 0


def test_weighted_similarity_null_dimension_excluded_from_denominator():
    """A fingerprint with only sequence data should score 1.0 against itself,
    not be penalised by the absent timing/protocol/credential/target weights."""
    fp = _make_fp(sequence=_FULL_SEQUENCE)
    result = compute_weighted_similarity(fp, fp)
    assert result.weighted_total == pytest.approx(1.0, abs=1e-4)
    assert result.dimensions_used == 1


def test_weighted_similarity_dimensions_used_count():
    fp = _make_fp(timing=_FULL_TIMING, target=_FULL_TARGET)
    result = compute_weighted_similarity(fp, fp)
    assert result.dimensions_used == 2


def test_weighted_similarity_result_has_all_fields():
    fp = _make_fp(sequence=_FULL_SEQUENCE)
    result = compute_weighted_similarity(fp, fp)
    d = result.as_dict()
    assert "timing_similarity" in d
    assert "sequence_similarity" in d
    assert "protocol_similarity" in d
    assert "credential_similarity" in d
    assert "target_similarity" in d
    assert "weighted_total" in d
    assert "dimensions_used" in d


def test_weighted_similarity_different_fps_below_one():
    fp1 = _make_fp(
        sequence={"port_sequence": [22, 80], "event_type_sequence": [], "credential_sequence": []}
    )
    fp2 = _make_fp(
        sequence={
            "port_sequence": [443, 8080],
            "event_type_sequence": [],
            "credential_sequence": [],
        }
    )
    result = compute_weighted_similarity(fp1, fp2)
    assert result.weighted_total < 0.5


def test_weighted_similarity_no_raw_values_in_result():
    """SimilarityResult must contain only numeric scores — no strings, no raw data."""
    fp = _make_fp(sequence=_FULL_SEQUENCE, target=_FULL_TARGET)
    result = compute_weighted_similarity(fp, fp)
    d = result.as_dict()
    for key, val in d.items():
        assert val is None or isinstance(
            val, int | float
        ), f"Field {key!r} has non-numeric value {val!r}"
