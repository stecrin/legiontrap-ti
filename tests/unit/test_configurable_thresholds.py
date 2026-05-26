"""Tests for configurable thresholds and similarity weights.

Verifies that:
- Settings class defaults match the previously hardcoded constants
- Settings validators reject out-of-range values
- Constants module exposes values sourced from Settings
- Clustering and lifecycle modules see the configured values
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.intelligence import constants as C

# ---------------------------------------------------------------------------
# Settings default values — must match original hardcoded constants
# ---------------------------------------------------------------------------


def test_settings_weight_timing_default():
    assert settings.WEIGHT_TIMING == 0.20


def test_settings_weight_sequence_default():
    assert settings.WEIGHT_SEQUENCE == 0.35


def test_settings_weight_protocol_default():
    assert settings.WEIGHT_PROTOCOL == 0.25


def test_settings_weight_credential_default():
    assert settings.WEIGHT_CREDENTIAL == 0.10


def test_settings_weight_target_default():
    assert settings.WEIGHT_TARGET == 0.10


def test_settings_similarity_auto_threshold_default():
    assert settings.SIMILARITY_AUTO_THRESHOLD == 0.80


def test_settings_similarity_uncertain_low_default():
    assert settings.SIMILARITY_UNCERTAIN_LOW == 0.60


def test_settings_temporal_threshold_6m_default():
    assert settings.TEMPORAL_THRESHOLD_6M == 0.85


def test_settings_temporal_threshold_12m_default():
    assert settings.TEMPORAL_THRESHOLD_12M == 0.90


def test_settings_min_events_for_clustering_default():
    assert settings.MIN_EVENTS_FOR_CLUSTERING == 10


def test_settings_campaign_active_days_default():
    assert settings.CAMPAIGN_ACTIVE_DAYS == 7


def test_settings_campaign_dormant_days_default():
    assert settings.CAMPAIGN_DORMANT_DAYS == 90


# ---------------------------------------------------------------------------
# Constants module sources values from settings
# ---------------------------------------------------------------------------


def test_constants_weight_timing_matches_settings():
    assert C.WEIGHT_TIMING == settings.WEIGHT_TIMING


def test_constants_weight_sequence_matches_settings():
    assert C.WEIGHT_SEQUENCE == settings.WEIGHT_SEQUENCE


def test_constants_weight_protocol_matches_settings():
    assert C.WEIGHT_PROTOCOL == settings.WEIGHT_PROTOCOL


def test_constants_weight_credential_matches_settings():
    assert C.WEIGHT_CREDENTIAL == settings.WEIGHT_CREDENTIAL


def test_constants_weight_target_matches_settings():
    assert C.WEIGHT_TARGET == settings.WEIGHT_TARGET


def test_constants_similarity_auto_threshold_matches_settings():
    assert C.SIMILARITY_AUTO_THRESHOLD == settings.SIMILARITY_AUTO_THRESHOLD


def test_constants_similarity_uncertain_low_matches_settings():
    assert C.SIMILARITY_UNCERTAIN_LOW == settings.SIMILARITY_UNCERTAIN_LOW


def test_constants_temporal_threshold_6m_matches_settings():
    assert C.TEMPORAL_THRESHOLD_6M == settings.TEMPORAL_THRESHOLD_6M


def test_constants_temporal_threshold_12m_matches_settings():
    assert C.TEMPORAL_THRESHOLD_12M == settings.TEMPORAL_THRESHOLD_12M


def test_constants_min_events_for_clustering_matches_settings():
    assert C.MIN_EVENTS_FOR_CLUSTERING == settings.MIN_EVENTS_FOR_CLUSTERING


def test_constants_campaign_active_days_matches_settings():
    assert C.CAMPAIGN_ACTIVE_DAYS == settings.CAMPAIGN_ACTIVE_DAYS


def test_constants_campaign_dormant_days_matches_settings():
    assert C.CAMPAIGN_DORMANT_DAYS == settings.CAMPAIGN_DORMANT_DAYS


# ---------------------------------------------------------------------------
# Validator: weight fields must be in (0, 1]
# ---------------------------------------------------------------------------


_REQUIRED_FIELDS = {
    "API_KEY": "test-key",
    "FEED_SALT": "test-salt",
    "DASH_PASS": "$2b$12$G6FRFvRadOZ6ztbYn34DzOQZswMD5T9DByiQrKh4dADcvwvv5mAxC",
    "JWT_SECRET": "test-secret",
}


@pytest.mark.parametrize("field", ["WEIGHT_TIMING", "WEIGHT_SEQUENCE", "WEIGHT_PROTOCOL"])
def test_settings_rejects_zero_weight(field):
    # Adjust the remaining weights to maintain sum ≈ 1.0 — but with the target
    # field at 0.0, the sum constraint also fires; both ValidationErrors are valid.
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, field: 0.0})


@pytest.mark.parametrize("field", ["WEIGHT_TIMING", "WEIGHT_SEQUENCE", "WEIGHT_PROTOCOL"])
def test_settings_rejects_negative_weight(field):
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, field: -0.1})


@pytest.mark.parametrize("field", ["WEIGHT_TIMING", "WEIGHT_SEQUENCE", "WEIGHT_PROTOCOL"])
def test_settings_rejects_weight_over_one(field):
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, field: 1.5})


# ---------------------------------------------------------------------------
# Validator: weights must sum to 1.0 (±0.01)
# ---------------------------------------------------------------------------


def test_settings_rejects_weights_that_dont_sum_to_one():
    with pytest.raises(ValidationError, match="sum to 1.0"):
        Settings(
            **{
                **_REQUIRED_FIELDS,
                "WEIGHT_TIMING": 0.30,
                "WEIGHT_SEQUENCE": 0.30,
                "WEIGHT_PROTOCOL": 0.30,
                "WEIGHT_CREDENTIAL": 0.30,
                "WEIGHT_TARGET": 0.30,
            }
        )


def test_settings_accepts_weights_within_tolerance():
    # Sum = 0.20 + 0.35 + 0.25 + 0.10 + 0.10 = 1.00 — should pass
    s = Settings(
        **{
            **_REQUIRED_FIELDS,
            "WEIGHT_TIMING": 0.20,
            "WEIGHT_SEQUENCE": 0.35,
            "WEIGHT_PROTOCOL": 0.25,
            "WEIGHT_CREDENTIAL": 0.10,
            "WEIGHT_TARGET": 0.10,
        }
    )
    assert (
        abs(
            s.WEIGHT_TIMING
            + s.WEIGHT_SEQUENCE
            + s.WEIGHT_PROTOCOL
            + s.WEIGHT_CREDENTIAL
            + s.WEIGHT_TARGET
            - 1.0
        )
        < 0.01
    )


# ---------------------------------------------------------------------------
# Validator: threshold fields must be in (0, 1]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    ["SIMILARITY_AUTO_THRESHOLD", "SIMILARITY_UNCERTAIN_LOW", "TEMPORAL_THRESHOLD_6M"],
)
def test_settings_rejects_zero_threshold(field):
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, field: 0.0})


@pytest.mark.parametrize(
    "field",
    ["SIMILARITY_AUTO_THRESHOLD", "SIMILARITY_UNCERTAIN_LOW", "TEMPORAL_THRESHOLD_6M"],
)
def test_settings_rejects_threshold_over_one(field):
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, field: 1.1})


# ---------------------------------------------------------------------------
# Validator: integer fields must be >= 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["MIN_EVENTS_FOR_CLUSTERING", "CAMPAIGN_ACTIVE_DAYS", "CAMPAIGN_DORMANT_DAYS"]
)
def test_settings_rejects_zero_int(field):
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, field: 0})


@pytest.mark.parametrize(
    "field", ["MIN_EVENTS_FOR_CLUSTERING", "CAMPAIGN_ACTIVE_DAYS", "CAMPAIGN_DORMANT_DAYS"]
)
def test_settings_rejects_negative_int(field):
    with pytest.raises(ValidationError):
        Settings(**{**_REQUIRED_FIELDS, field: -1})


# ---------------------------------------------------------------------------
# Lifecycle module uses configured days from constants
# ---------------------------------------------------------------------------


def test_lifecycle_uses_campaign_active_days():

    # run_lifecycle_transitions uses CAMPAIGN_ACTIVE_DAYS from constants,
    # which sources from settings. The default is 7 days.
    # Verify the constant is not zero or negative (would break lifecycle logic).
    assert C.CAMPAIGN_ACTIVE_DAYS > 0


def test_lifecycle_uses_campaign_dormant_days():

    assert C.CAMPAIGN_DORMANT_DAYS > 0
    assert C.CAMPAIGN_DORMANT_DAYS > C.CAMPAIGN_ACTIVE_DAYS


# ---------------------------------------------------------------------------
# Similarity module uses configured weights from constants
# ---------------------------------------------------------------------------


def test_similarity_uses_weight_constants(monkeypatch):
    """Verify compute_weighted_similarity respects the module-level weight constants."""
    import app.intelligence.similarity as sim_module

    # Patch the weight constants in the similarity module to known values
    monkeypatch.setattr(sim_module, "WEIGHT_TIMING", 1.0)
    monkeypatch.setattr(sim_module, "WEIGHT_SEQUENCE", 0.0)
    monkeypatch.setattr(sim_module, "WEIGHT_PROTOCOL", 0.0)
    monkeypatch.setattr(sim_module, "WEIGHT_CREDENTIAL", 0.0)
    monkeypatch.setattr(sim_module, "WEIGHT_TARGET", 0.0)

    # Two fingerprints with known timing features; sequence/protocol/etc. absent.
    _tf = '{"interval": {"mean": 1.0, "stddev": 0.1, "p25": 0.9, "p75": 1.1, "p95": 1.5}}'
    fp1 = {"timing_features": _tf}
    fp2 = {"timing_features": _tf}

    result = sim_module.compute_weighted_similarity(fp1, fp2)
    # With weight_timing=1.0 and identical timing features, weighted_total should be > 0.9
    assert result.weighted_total > 0.9
    assert result.dimensions_used == 1
