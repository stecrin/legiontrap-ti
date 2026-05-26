"""Campaign assignment service — maps a new fingerprint to a campaign (§8.2).

Entry point: assign_to_campaign(ip, fp, repo, now)

Algorithm per §8.2 and §12.3:
  1. Gate: confidence < 0.20 → skip (sparse fingerprint, §12.6)
  2. Already a member → update last_active, record observation, return
  3. Fetch candidate campaigns (active / dormant / reactivated)
  4. For each candidate, compute weighted similarity; apply temporal threshold
     bump if the campaign has been dormant for 6+ or 12+ months (§12.3)
  5. Select the highest-scoring candidate above SIMILARITY_UNCERTAIN_LOW
  6. Decision:
       score ≥ effective_auto_threshold  → automatic_association
       score ≥ SIMILARITY_UNCERTAIN_LOW  → uncertain_association
       no candidate above uncertain low  → new_campaign
  7. Persist: add member, insert observation, update campaign

Explainability (§12.7):
  Every association stores a JSON explanation in campaign_observations.notes
  containing per-dimension similarity scores, weighted total, threshold
  applied, and decision label.

Deterministic: same inputs always produce the same output (§11, §12.7).
No ML, no external APIs, no raw credentials or IPs in outputs.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.intelligence.constants import (
    SIMILARITY_AUTO_THRESHOLD,
    SIMILARITY_UNCERTAIN_LOW,
    TEMPORAL_THRESHOLD_6M,
    TEMPORAL_THRESHOLD_12M,
)
from app.intelligence.similarity import SimilarityResult, compute_weighted_similarity

if TYPE_CHECKING:
    from app.db.repository import EventRepository

# ---------------------------------------------------------------------------
# Decision labels
# ---------------------------------------------------------------------------

DECISION_SKIPPED_SPARSE = "skipped_sparse"
DECISION_EXISTING_MEMBER = "existing_member"
DECISION_AUTO_ASSOCIATION = "automatic_association"
DECISION_UNCERTAIN_ASSOCIATION = "uncertain_association"
DECISION_NEW_CAMPAIGN = "new_campaign"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ClusteringDecision:
    """Full record of a single campaign assignment decision."""

    decision: str
    campaign_id: str | None
    similarity: SimilarityResult | None
    threshold_applied: float
    reason: str
    is_reactivation: bool = field(default=False)
    dormancy_gap_days: float | None = field(default=None)


# ---------------------------------------------------------------------------
# Temporal threshold helpers
# ---------------------------------------------------------------------------


def _get_effective_auto_threshold(
    campaign_last_seen: str,
    now: datetime,
) -> float:
    """Return the auto-association threshold adjusted for temporal gap (§12.3).

    The base threshold (SIMILARITY_AUTO_THRESHOLD = 0.80) is raised when
    the campaign has been dormant for a long time, because the probability
    that similar-looking activity is coincidental increases with time.
    """
    try:
        last_dt = datetime.fromisoformat(campaign_last_seen.replace("Z", "+00:00")).astimezone(UTC)
        gap_days = (now - last_dt).days
    except (ValueError, AttributeError, TypeError):
        return SIMILARITY_AUTO_THRESHOLD

    if gap_days > 365:
        return TEMPORAL_THRESHOLD_12M
    if gap_days > 182:
        return TEMPORAL_THRESHOLD_6M
    return SIMILARITY_AUTO_THRESHOLD


def _dormancy_gap_days(campaign_last_seen: str, now: datetime) -> float | None:
    """Return days between campaign_last_seen and now, or None on parse failure."""
    try:
        last_dt = datetime.fromisoformat(campaign_last_seen.replace("Z", "+00:00")).astimezone(UTC)
        return max(0.0, (now - last_dt).total_seconds() / 86400.0)
    except (ValueError, AttributeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def assign_to_campaign(
    ip: str,
    fp: dict[str, Any],
    repo: EventRepository,
    now: datetime | None = None,
) -> ClusteringDecision:
    """Assign ip's fingerprint to an existing or new campaign.

    fp must be a behavioral_fingerprint dict as returned by
    EventRepository.get_behavioral_fingerprint() — feature columns are JSON
    strings (or None).

    now is injectable for deterministic testing; defaults to UTC now.
    """
    if now is None:
        now = datetime.now(UTC)
    now_str = now.isoformat()

    # Gate 1: Sparse fingerprints do not enter clustering (§12.6).
    confidence: float = float(fp.get("confidence", 0.0))
    if confidence < 0.20:
        return ClusteringDecision(
            decision=DECISION_SKIPPED_SPARSE,
            campaign_id=None,
            similarity=None,
            threshold_applied=0.20,
            reason=(f"fingerprint confidence {confidence:.4f} below " "clustering threshold 0.20"),
        )

    # Gate 2: IP is already assigned to a campaign.
    existing = repo.get_campaign_member_by_ip(ip)
    if existing is not None:
        campaign_id: str = existing["campaign_id"]
        event_count = int(fp.get("event_count_at_computation", 0))
        repo.update_campaign_member_last_active(campaign_id, ip, now_str)
        repo.insert_campaign_observation(
            campaign_id=campaign_id,
            source_ip=ip,
            observed_at=now_str,
            event_count=event_count,
            is_reactivation=False,
            dormancy_gap_days=None,
            notes=None,
        )
        repo.update_campaign_on_association(
            campaign_id=campaign_id,
            last_seen=now_str,
            updated_at=now_str,
            new_member_ip_count_delta=0,
            is_reactivation=False,
        )
        return ClusteringDecision(
            decision=DECISION_EXISTING_MEMBER,
            campaign_id=campaign_id,
            similarity=None,
            threshold_applied=0.0,
            reason="IP already assigned; observation and last_active updated",
        )

    # Step 3: Fetch candidate campaigns.
    candidates = repo.get_campaigns_for_clustering()

    # Step 4: Find best candidate above the uncertain-low threshold.
    best_campaign_id: str | None = None
    best_sim: SimilarityResult | None = None
    best_auto_threshold: float = SIMILARITY_AUTO_THRESHOLD
    best_last_seen: str | None = None
    best_status: str | None = None

    for candidate in candidates:
        sim = compute_weighted_similarity(fp, candidate)
        score = sim.weighted_total

        effective_auto = _get_effective_auto_threshold(candidate["last_seen"], now)

        if score >= SIMILARITY_UNCERTAIN_LOW and (
            best_sim is None or score > best_sim.weighted_total
        ):
            best_campaign_id = candidate["campaign_id"]
            best_sim = sim
            best_auto_threshold = effective_auto
            best_last_seen = candidate["last_seen"]
            best_status = candidate["status"]

    # Step 5–7: Decision and persistence.
    if best_sim is not None:
        score = best_sim.weighted_total
        is_reactivation = best_status == "dormant"
        gap_days = _dormancy_gap_days(best_last_seen, now) if is_reactivation else None

        decision = (
            DECISION_AUTO_ASSOCIATION
            if score >= best_auto_threshold
            else DECISION_UNCERTAIN_ASSOCIATION
        )

        explanation = {
            **best_sim.as_dict(),
            "threshold_applied": best_auto_threshold,
            "decision": decision,
        }
        notes = json.dumps(explanation, separators=(",", ":"))
        event_count = int(fp.get("event_count_at_computation", 0))

        repo.add_campaign_member(
            campaign_id=best_campaign_id,
            source_ip=ip,
            confidence=score,
            added_at=now_str,
            last_active=now_str,
        )
        repo.insert_campaign_observation(
            campaign_id=best_campaign_id,
            source_ip=ip,
            observed_at=now_str,
            event_count=event_count,
            is_reactivation=is_reactivation,
            dormancy_gap_days=gap_days,
            notes=notes,
        )
        repo.update_campaign_on_association(
            campaign_id=best_campaign_id,
            last_seen=now_str,
            updated_at=now_str,
            new_member_ip_count_delta=1,
            is_reactivation=is_reactivation,
        )

        return ClusteringDecision(
            decision=decision,
            campaign_id=best_campaign_id,
            similarity=best_sim,
            threshold_applied=best_auto_threshold,
            reason=f"similarity {score:.4f} vs auto threshold {best_auto_threshold:.2f}",
            is_reactivation=is_reactivation,
            dormancy_gap_days=gap_days,
        )

    # No suitable candidate — create a new campaign.
    return _create_new_campaign(ip, fp, repo, now_str)


# ---------------------------------------------------------------------------
# New campaign creation
# ---------------------------------------------------------------------------


def _create_new_campaign(
    ip: str,
    fp: dict[str, Any],
    repo: EventRepository,
    now_str: str,
) -> ClusteringDecision:
    """Create a new campaign for ip and return the decision."""
    from app.intelligence.campaign_names import generate_campaign_name

    campaign_id = str(uuid.uuid4())
    name = generate_campaign_name(campaign_id)
    event_count = int(fp.get("event_count_at_computation", 0))
    confidence = float(fp.get("confidence", 0.5))

    repo.create_campaign(
        campaign_id=campaign_id,
        name=name,
        status="active",
        confidence=confidence,
        first_seen=now_str,
        last_seen=now_str,
        member_ip_count=1,
        created_at=now_str,
        updated_at=now_str,
    )
    repo.add_campaign_member(
        campaign_id=campaign_id,
        source_ip=ip,
        confidence=confidence,
        added_at=now_str,
        last_active=now_str,
    )
    repo.insert_campaign_observation(
        campaign_id=campaign_id,
        source_ip=ip,
        observed_at=now_str,
        event_count=event_count,
        is_reactivation=False,
        dormancy_gap_days=None,
        notes=None,
    )

    return ClusteringDecision(
        decision=DECISION_NEW_CAMPAIGN,
        campaign_id=campaign_id,
        similarity=None,
        threshold_applied=SIMILARITY_UNCERTAIN_LOW,
        reason="no existing campaign above similarity threshold; new campaign created",
    )
