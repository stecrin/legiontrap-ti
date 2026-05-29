"""Per-campaign similarity weight profile computation — Phase 7 Group A.

Reads analyst review decisions from campaign_observations.analyst_review_json
and adjusts per-campaign dimension weights accordingly.

Algorithm (per §6.1 of Phase 7 blueprint):
  1. Fetch all reviewed uncertain-association observations for the campaign.
  2. Skip observation IDs already present in the adjustment log (idempotent).
  3. For each new confirmed review:
       - identify dimensions with per-dimension score > WEIGHT_HIGH_SCORE_GATE
       - nudge those dimension weights UP by WEIGHT_REVIEW_NUDGE
  4. For each new denied review:
       - identify dimensions with per-dimension score > WEIGHT_HIGH_SCORE_GATE
       - nudge those dimension weights DOWN by WEIGHT_REVIEW_NUDGE
  5. Clamp each weight to [WEIGHT_FLOOR, WEIGHT_CEILING].
  6. Renormalize so all five weights sum to 1.0.
  7. Persist the updated profile only when review_count >= WEIGHT_PROFILE_MIN_REVIEWS.

Idempotency: the adjustment log stores processed observation IDs.  Running
process_campaign_weight_profile() multiple times on the same campaign with the
same review state produces the same result.

Determinism: same set of reviews + same configuration → same weights.

No AI imports.  No external calls.  No campaign or fingerprint mutations.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from app.db.repository import EventRepository

logger = logging.getLogger(__name__)

_DIMS = ("timing", "sequence", "protocol", "credential", "target")

# Mapping from observation notes field names to short dimension names.
_SCORE_KEY_MAP = {
    "timing_similarity": "timing",
    "sequence_similarity": "sequence",
    "protocol_similarity": "protocol",
    "credential_similarity": "credential",
    "target_similarity": "target",
}


def _default_weights() -> dict[str, float]:
    return {
        "timing": settings.WEIGHT_TIMING,
        "sequence": settings.WEIGHT_SEQUENCE,
        "protocol": settings.WEIGHT_PROTOCOL,
        "credential": settings.WEIGHT_CREDENTIAL,
        "target": settings.WEIGHT_TARGET,
    }


def _clamp_and_renormalize(
    weights: dict[str, float],
    floor: float,
    ceiling: float,
) -> dict[str, float]:
    """Clamp each weight to [floor, ceiling] then renormalize to sum to 1.0."""
    clamped = {d: max(floor, min(ceiling, weights[d])) for d in _DIMS}
    total = sum(clamped[d] for d in _DIMS)
    if total <= 0:
        return _default_weights()
    return {d: round(clamped[d] / total, 8) for d in _DIMS}


def _extract_dim_scores(notes_json: str | None) -> dict[str, float]:
    """Parse per-dimension scores from a campaign_observations.notes JSON string.

    Returns an empty dict on parse failure or missing keys.
    """
    if not notes_json:
        return {}
    try:
        parsed = json.loads(notes_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    scores: dict[str, float] = {}
    for long_key, short_key in _SCORE_KEY_MAP.items():
        val = parsed.get(long_key)
        if isinstance(val, int | float):
            scores[short_key] = float(val)
    return scores


def _apply_one_review(
    weights: dict[str, float],
    dim_scores: dict[str, float],
    decision: str,
    nudge: float,
    floor: float,
    ceiling: float,
    high_score_gate: float,
) -> tuple[dict[str, float], dict[str, float]]:
    """Apply a single analyst review decision to current weights.

    Returns (new_weights_after_clamp_renorm, raw_dimension_adjustments).
    Adjustments are the nudge values before clamping; they are recorded in
    the adjustment log for auditability.
    """
    direction = 1.0 if decision == "analyst_confirmed" else -1.0
    adjustments: dict[str, float] = {}
    raw: dict[str, float] = dict(weights)

    for dim in _DIMS:
        score = dim_scores.get(dim)
        adj = direction * nudge if score is not None and score > high_score_gate else 0.0
        adjustments[dim] = adj
        raw[dim] = raw[dim] + adj

    new_weights = _clamp_and_renormalize(raw, floor, ceiling)
    return new_weights, adjustments


def process_campaign_weight_profile(
    campaign_id: str,
    repo: EventRepository,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Recompute and persist the weight profile for campaign_id.

    Fetches all reviewed uncertain-association observations for the campaign,
    skips already-processed observation IDs, applies new reviews, and persists
    the result.

    Returns the updated profile dict, or None when fewer than
    WEIGHT_PROFILE_MIN_REVIEWS reviews have been processed.

    Safe to call multiple times (idempotent).
    """
    if now is None:
        now = datetime.now(UTC)
    now_str = now.isoformat()

    nudge = settings.WEIGHT_REVIEW_NUDGE
    floor = settings.WEIGHT_FLOOR
    ceiling = settings.WEIGHT_CEILING
    min_reviews = settings.WEIGHT_PROFILE_MIN_REVIEWS
    high_score_gate = settings.WEIGHT_HIGH_SCORE_GATE

    # Load existing profile to get current weights and already-processed IDs.
    existing = repo.get_weight_profile(campaign_id)
    if existing:
        current_weights = dict(existing["weights"])
        adjustment_log: list[dict[str, Any]] = list(existing["adjustment_log"])
        confirmed_count = existing["confirmed_count"]
        denied_count = existing["denied_count"]
    else:
        current_weights = _default_weights()
        adjustment_log = []
        confirmed_count = 0
        denied_count = 0

    processed_obs_ids: set[str] = {entry["observation_id"] for entry in adjustment_log}

    # Fetch all reviewed uncertain observations for this campaign.
    observations = repo.list_uncertain_observations(
        campaign_id=campaign_id,
        include_reviewed=True,
    )
    reviewed = [
        obs
        for obs in observations
        if obs.get("analyst_review_json") is not None and obs["id"] not in processed_obs_ids
    ]

    if not reviewed:
        # Nothing new to process.
        if existing and existing["review_count"] >= min_reviews:
            return existing
        return None

    for obs in reviewed:
        try:
            review = json.loads(obs["analyst_review_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(review, dict):
            continue

        decision = review.get("decision")
        if decision not in {"analyst_confirmed", "analyst_denied"}:
            continue

        reviewed_at = review.get("reviewed_at", now_str)
        dim_scores = _extract_dim_scores(obs.get("notes"))

        new_weights, adjustments = _apply_one_review(
            current_weights,
            dim_scores,
            decision,
            nudge,
            floor,
            ceiling,
            high_score_gate,
        )

        adjustment_log.append(
            {
                "observation_id": obs["id"],
                "review_decision": decision,
                "reviewed_at": reviewed_at,
                "dimension_adjustments": adjustments,
                "weights_after": dict(new_weights),
            }
        )
        current_weights = new_weights

        if decision == "analyst_confirmed":
            confirmed_count += 1
        else:
            denied_count += 1

    review_count = confirmed_count + denied_count

    if review_count < min_reviews:
        # Not enough reviews yet to create a profile.
        return None

    repo.upsert_weight_profile(
        campaign_id=campaign_id,
        weights=current_weights,
        review_count=review_count,
        confirmed_count=confirmed_count,
        denied_count=denied_count,
        adjustment_log=adjustment_log,
        computed_at=now_str,
        updated_at=now_str,
    )

    return repo.get_weight_profile(campaign_id)


def process_all_campaign_weight_profiles(
    repo: EventRepository,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Recompute weight profiles for all campaigns with reviewed observations.

    Idempotent.  Per-campaign failures are logged but do not interrupt the
    processing of remaining campaigns.
    """
    if now is None:
        now = datetime.now(UTC)

    campaign_ids = repo.list_all_campaign_ids()
    updated = 0
    skipped = 0

    for cid in campaign_ids:
        try:
            result = process_campaign_weight_profile(cid, repo, now)
            if result is not None:
                updated += 1
            else:
                skipped += 1
        except Exception:
            logger.exception("Weight profile processing failed for campaign_id=%s", cid)
            skipped += 1

    return {
        "campaigns_evaluated": len(campaign_ids),
        "profiles_updated": updated,
        "skipped_insufficient_reviews": skipped,
        "processed_at": now.isoformat(),
    }
