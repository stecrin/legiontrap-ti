"""Campaign evidence quality and density classification — Phase 7 Group A3.

Pure computation module.  No database access.  No external calls.
All inputs are passed as arguments; all outputs are deterministic.

Classification hierarchy (checked in order, first match wins):
  sparse      — no representative fingerprint (analytics job has not produced one)
  mature      — density_score >= 0.70
  established — density_score >= 0.35
  emerging    — density_score > 0 (has fingerprint, below established)

Density score [0.0, 1.0]: weighted sum of four normalised sub-scores drawn
from configurable thresholds in app.core.config.settings:

  obs_score    = min(1, observation_count / SPARSE_OBS_MATURE)       weight 0.35
  ip_score     = min(1, unique_ip_count   / SPARSE_IP_MATURE)         weight 0.25
  age_score    = min(1, age_span_hours    / SPARSE_AGE_HOURS_MATURE)  weight 0.30
  review_score = min(1, review_count      / 5)                        weight 0.10

Campaigns without a representative fingerprint always receive
density_score = 0.0 and classification = "sparse".

No AI.  No ML.  No actor or fingerprint table references.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

# Classification bucket thresholds (not operator-configurable — derived from
# the calibrated normalisation thresholds in settings).
_DENSITY_MATURE_THRESHOLD: float = 0.70
_DENSITY_ESTABLISHED_THRESHOLD: float = 0.35

# Denominator for review_score normalisation (5 reviews = full score).
_REVIEW_FULL_SCORE: int = 5

# Component weights (must sum to 1.0).
_W_OBS: float = 0.35
_W_IP: float = 0.25
_W_AGE: float = 0.30
_W_REVIEW: float = 0.10


@dataclass(frozen=True)
class DensityComponents:
    """Per-dimension normalised sub-scores before weighting."""

    obs_score: float
    ip_score: float
    age_score: float
    review_score: float


@dataclass(frozen=True)
class DensityResult:
    """Full density metrics and classification for a campaign."""

    observation_count: int
    unique_ip_count: int
    review_count: int
    age_span_hours: float
    has_fingerprint: bool
    density_score: float
    classification: str  # sparse | emerging | established | mature
    components: DensityComponents


def age_span_hours(first_seen: str | None, last_seen: str | None) -> float:
    """Return campaign age span in fractional hours.  0.0 on parse failure."""
    if not first_seen or not last_seen:
        return 0.0
    try:
        fs = datetime.fromisoformat(first_seen.replace("Z", "+00:00")).astimezone(UTC)
        ls = datetime.fromisoformat(last_seen.replace("Z", "+00:00")).astimezone(UTC)
        return round(max(0.0, (ls - fs).total_seconds() / 3600.0), 4)
    except (ValueError, AttributeError, TypeError):
        return 0.0


def compute_density_score(
    observation_count: int,
    unique_ip_count: int,
    age_hours: float,
    review_count: int,
) -> tuple[float, DensityComponents]:
    """Return (density_score, DensityComponents) for campaigns that have a fingerprint."""
    obs_s = min(1.0, observation_count / max(1, settings.SPARSE_OBS_MATURE))
    ip_s = min(1.0, unique_ip_count / max(1, settings.SPARSE_IP_MATURE))
    age_s = min(1.0, age_hours / max(0.001, settings.SPARSE_AGE_HOURS_MATURE))
    rev_s = min(1.0, review_count / _REVIEW_FULL_SCORE)

    components = DensityComponents(
        obs_score=round(obs_s, 4),
        ip_score=round(ip_s, 4),
        age_score=round(age_s, 4),
        review_score=round(rev_s, 4),
    )
    score = round(
        _W_OBS * obs_s + _W_IP * ip_s + _W_AGE * age_s + _W_REVIEW * rev_s,
        4,
    )
    return score, components


def classify(has_fingerprint: bool, density_score: float) -> str:
    """Return the deterministic classification string."""
    if not has_fingerprint:
        return "sparse"
    if density_score >= _DENSITY_MATURE_THRESHOLD:
        return "mature"
    if density_score >= _DENSITY_ESTABLISHED_THRESHOLD:
        return "established"
    return "emerging"


def _resolve_has_fingerprint(campaign: dict[str, Any]) -> bool:
    """Return fingerprint presence from either the full JSON or a pre-computed bool flag.

    list_campaigns_with_fingerprint_status stores 'has_fingerprint' (bool).
    get_campaign_with_fingerprint stores 'representative_fingerprint_json' (str | None).
    list_sparse_campaigns sets 'has_fingerprint' = False explicitly.
    This helper handles all three shapes.
    """
    if "representative_fingerprint_json" in campaign:
        return bool(campaign["representative_fingerprint_json"])
    return bool(campaign.get("has_fingerprint", False))


def compute_campaign_density(
    campaign: dict[str, Any],
    observation_count: int,
    review_count: int,
) -> DensityResult:
    """Compute the full density result for a single campaign dict.

    campaign must contain: first_seen, last_seen, member_ip_count.
    It may contain either representative_fingerprint_json (str | None) or
    has_fingerprint (bool) — both forms are accepted.
    observation_count and review_count are supplied by the DB layer.
    """
    has_fp = _resolve_has_fingerprint(campaign)
    age_h = age_span_hours(campaign.get("first_seen"), campaign.get("last_seen"))
    unique_ips = int(campaign.get("member_ip_count") or 0)

    if not has_fp:
        zero = DensityComponents(obs_score=0.0, ip_score=0.0, age_score=0.0, review_score=0.0)
        return DensityResult(
            observation_count=observation_count,
            unique_ip_count=unique_ips,
            review_count=review_count,
            age_span_hours=age_h,
            has_fingerprint=False,
            density_score=0.0,
            classification="sparse",
            components=zero,
        )

    score, components = compute_density_score(
        observation_count=observation_count,
        unique_ip_count=unique_ips,
        age_hours=age_h,
        review_count=review_count,
    )
    return DensityResult(
        observation_count=observation_count,
        unique_ip_count=unique_ips,
        review_count=review_count,
        age_span_hours=age_h,
        has_fingerprint=True,
        density_score=score,
        classification=classify(has_fingerprint=True, density_score=score),
        components=components,
    )
