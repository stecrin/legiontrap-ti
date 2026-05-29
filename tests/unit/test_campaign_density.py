"""Unit tests for Phase 7 Group A3 — campaign density and classification.

Tests cover:
  - age_span_hours: correct computation, 0.0 on bad input
  - compute_density_score: correct weighting, boundary clamping
  - classify: all four classification buckets, boundary conditions
  - compute_campaign_density: sparse (no fingerprint), full density, determinism
  - No AI imports, no actor table references
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.intelligence.campaign_density import (
    _DENSITY_ESTABLISHED_THRESHOLD,
    _DENSITY_MATURE_THRESHOLD,
    DensityComponents,
    DensityResult,
    age_span_hours,
    classify,
    compute_campaign_density,
    compute_density_score,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings(
    obs_mature: int = 20,
    ip_mature: int = 5,
    age_hours_mature: float = 168.0,
    obs_established: int = 8,
    age_hours_established: float = 24.0,
) -> MagicMock:
    return MagicMock(
        SPARSE_OBS_MATURE=obs_mature,
        SPARSE_IP_MATURE=ip_mature,
        SPARSE_AGE_HOURS_MATURE=age_hours_mature,
        SPARSE_OBS_ESTABLISHED=obs_established,
        SPARSE_AGE_HOURS_ESTABLISHED=age_hours_established,
    )


def _patch_settings(monkeypatch, **kwargs) -> None:
    monkeypatch.setattr(
        "app.intelligence.campaign_density.settings",
        _mock_settings(**kwargs),
    )


def _campaign(
    first_seen: str = "2026-05-01T00:00:00+00:00",
    last_seen: str = "2026-05-08T00:00:00+00:00",
    member_ip_count: int = 3,
    representative_fingerprint_json: str | None = '{"timing_features": null}',
) -> dict:
    return {
        "first_seen": first_seen,
        "last_seen": last_seen,
        "member_ip_count": member_ip_count,
        "representative_fingerprint_json": representative_fingerprint_json,
    }


# ---------------------------------------------------------------------------
# age_span_hours
# ---------------------------------------------------------------------------


def test_age_span_hours_one_week():
    hours = age_span_hours("2026-05-01T00:00:00+00:00", "2026-05-08T00:00:00+00:00")
    assert hours == pytest.approx(168.0, abs=0.01)


def test_age_span_hours_same_timestamp():
    hours = age_span_hours("2026-05-01T00:00:00+00:00", "2026-05-01T00:00:00+00:00")
    assert hours == 0.0


def test_age_span_hours_last_before_first_returns_zero():
    hours = age_span_hours("2026-05-08T00:00:00+00:00", "2026-05-01T00:00:00+00:00")
    assert hours == 0.0


def test_age_span_hours_none_inputs():
    assert age_span_hours(None, "2026-05-01T00:00:00+00:00") == 0.0
    assert age_span_hours("2026-05-01T00:00:00+00:00", None) == 0.0
    assert age_span_hours(None, None) == 0.0


def test_age_span_hours_invalid_string():
    assert age_span_hours("not-a-date", "also-not") == 0.0


def test_age_span_hours_36_hours():
    hours = age_span_hours("2026-05-01T00:00:00+00:00", "2026-05-02T12:00:00+00:00")
    assert hours == pytest.approx(36.0, abs=0.01)


# ---------------------------------------------------------------------------
# compute_density_score
# ---------------------------------------------------------------------------


def test_density_score_all_full(monkeypatch):
    _patch_settings(monkeypatch, obs_mature=20, ip_mature=5, age_hours_mature=168.0)
    score, components = compute_density_score(
        observation_count=20, unique_ip_count=5, age_hours=168.0, review_count=5
    )
    assert score == pytest.approx(1.0, abs=0.001)
    assert components.obs_score == pytest.approx(1.0)
    assert components.ip_score == pytest.approx(1.0)
    assert components.age_score == pytest.approx(1.0)
    assert components.review_score == pytest.approx(1.0)


def test_density_score_all_zero(monkeypatch):
    _patch_settings(monkeypatch)
    score, components = compute_density_score(
        observation_count=0, unique_ip_count=0, age_hours=0.0, review_count=0
    )
    assert score == 0.0
    assert components.obs_score == 0.0


def test_density_score_clamped_above_one(monkeypatch):
    _patch_settings(monkeypatch, obs_mature=20, ip_mature=5, age_hours_mature=168.0)
    score, components = compute_density_score(
        observation_count=1000, unique_ip_count=1000, age_hours=9999.0, review_count=100
    )
    assert score == pytest.approx(1.0, abs=0.001)
    assert components.obs_score == 1.0
    assert components.ip_score == 1.0
    assert components.age_score == 1.0
    assert components.review_score == 1.0


def test_density_score_half_each_dimension(monkeypatch):
    _patch_settings(monkeypatch, obs_mature=20, ip_mature=4, age_hours_mature=100.0)
    score, components = compute_density_score(
        observation_count=10, unique_ip_count=2, age_hours=50.0, review_count=0
    )
    assert components.obs_score == pytest.approx(0.5, abs=0.001)
    assert components.ip_score == pytest.approx(0.5, abs=0.001)
    assert components.age_score == pytest.approx(0.5, abs=0.001)
    assert components.review_score == 0.0
    # 0.35*0.5 + 0.25*0.5 + 0.30*0.5 + 0.10*0.0 = 0.5*0.9 = 0.45
    assert score == pytest.approx(0.45, abs=0.001)


def test_density_score_is_deterministic(monkeypatch):
    _patch_settings(monkeypatch)
    s1, _ = compute_density_score(10, 3, 50.0, 2)
    s2, _ = compute_density_score(10, 3, 50.0, 2)
    assert s1 == s2


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------


def test_classify_sparse_no_fingerprint():
    assert classify(has_fingerprint=False, density_score=1.0) == "sparse"


def test_classify_mature():
    assert classify(has_fingerprint=True, density_score=_DENSITY_MATURE_THRESHOLD) == "mature"
    assert classify(has_fingerprint=True, density_score=1.0) == "mature"


def test_classify_established():
    assert (
        classify(has_fingerprint=True, density_score=_DENSITY_ESTABLISHED_THRESHOLD)
        == "established"
    )
    assert (
        classify(has_fingerprint=True, density_score=_DENSITY_MATURE_THRESHOLD - 0.001)
        == "established"
    )


def test_classify_emerging():
    assert classify(has_fingerprint=True, density_score=0.01) == "emerging"
    assert (
        classify(has_fingerprint=True, density_score=_DENSITY_ESTABLISHED_THRESHOLD - 0.001)
        == "emerging"
    )


def test_classify_emerging_at_zero_with_fingerprint():
    assert classify(has_fingerprint=True, density_score=0.0) == "emerging"


# ---------------------------------------------------------------------------
# compute_campaign_density — sparse (no fingerprint)
# ---------------------------------------------------------------------------


def test_compute_density_sparse_no_fingerprint(monkeypatch):
    _patch_settings(monkeypatch)
    c = _campaign(representative_fingerprint_json=None)
    result = compute_campaign_density(c, observation_count=5, review_count=1)
    assert result.has_fingerprint is False
    assert result.density_score == 0.0
    assert result.classification == "sparse"
    assert isinstance(result.components, DensityComponents)
    assert result.observation_count == 5
    assert result.review_count == 1


def test_compute_density_sparse_zero_components(monkeypatch):
    _patch_settings(monkeypatch)
    c = _campaign(representative_fingerprint_json=None)
    result = compute_campaign_density(c, observation_count=0, review_count=0)
    assert result.components.obs_score == 0.0
    assert result.components.ip_score == 0.0
    assert result.components.age_score == 0.0
    assert result.components.review_score == 0.0


# ---------------------------------------------------------------------------
# compute_campaign_density — with fingerprint
# ---------------------------------------------------------------------------


def test_compute_density_with_fingerprint_is_not_sparse(monkeypatch):
    _patch_settings(monkeypatch)
    c = _campaign(representative_fingerprint_json='{"confidence": 0.8}')
    result = compute_campaign_density(c, observation_count=5, review_count=0)
    assert result.has_fingerprint is True
    assert result.classification != "sparse"


def test_compute_density_mature_campaign(monkeypatch):
    _patch_settings(monkeypatch, obs_mature=5, ip_mature=2, age_hours_mature=24.0)
    # Campaign that exceeds all thresholds
    c = _campaign(
        first_seen="2026-05-01T00:00:00+00:00",
        last_seen="2026-05-03T00:00:00+00:00",  # 48h > 24h mature
        member_ip_count=10,
    )
    result = compute_campaign_density(c, observation_count=20, review_count=5)
    assert result.classification == "mature"
    assert result.density_score >= _DENSITY_MATURE_THRESHOLD


def test_compute_density_emerging_new_campaign(monkeypatch):
    _patch_settings(monkeypatch, obs_mature=20, ip_mature=5, age_hours_mature=168.0)
    # Brand new campaign: 1 observation, 1 IP, 1 hour old
    c = _campaign(
        first_seen="2026-05-01T00:00:00+00:00",
        last_seen="2026-05-01T01:00:00+00:00",
        member_ip_count=1,
    )
    result = compute_campaign_density(c, observation_count=1, review_count=0)
    assert result.classification == "emerging"
    assert result.density_score < _DENSITY_ESTABLISHED_THRESHOLD


def test_compute_density_uses_member_ip_count(monkeypatch):
    _patch_settings(monkeypatch, ip_mature=4)
    c = _campaign(member_ip_count=4)
    result = compute_campaign_density(c, observation_count=0, review_count=0)
    assert result.unique_ip_count == 4
    assert result.components.ip_score == pytest.approx(1.0)


def test_compute_density_result_is_frozen():
    from app.intelligence.campaign_density import DensityComponents

    d = DensityResult(
        observation_count=1,
        unique_ip_count=1,
        review_count=0,
        age_span_hours=1.0,
        has_fingerprint=True,
        density_score=0.1,
        classification="emerging",
        components=DensityComponents(obs_score=0.1, ip_score=0.1, age_score=0.1, review_score=0.0),
    )
    with pytest.raises(AttributeError):
        d.classification = "mature"


def test_compute_density_deterministic(monkeypatch):
    _patch_settings(monkeypatch)
    c = _campaign(member_ip_count=3)
    r1 = compute_campaign_density(c, observation_count=10, review_count=2)
    r2 = compute_campaign_density(c, observation_count=10, review_count=2)
    assert r1.density_score == r2.density_score
    assert r1.classification == r2.classification


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def test_no_ai_imports_in_campaign_density():
    import importlib

    mod = importlib.import_module("app.intelligence.campaign_density")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "from app.ai" not in content
    assert "import app.ai" not in content


def test_no_actor_table_references_in_campaign_density():
    import importlib

    mod = importlib.import_module("app.intelligence.campaign_density")
    src = mod.__file__
    assert src is not None
    with open(src) as f:
        content = f.read()
    assert "actor_profiles" not in content
    assert "campaign_lineage" not in content
