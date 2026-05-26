"""Campaign lifecycle maintenance.

Deterministic status transitions based on time thresholds. No AI, no external
calls, no side effects beyond the repository writes the caller provides.

Transition rules (applied in this order):
  active/reactivated → dormant    when last_seen  < now - CAMPAIGN_ACTIVE_DAYS
  dormant            → historical when dormant_since < now - CAMPAIGN_DORMANT_DAYS

Ordering matters: the active→dormant pass runs first so that campaigns newly
marked dormant in this run are not immediately promoted to historical (their
dormant_since is just set to now).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.intelligence.constants import CAMPAIGN_ACTIVE_DAYS, CAMPAIGN_DORMANT_DAYS


def run_lifecycle_transitions(
    repo,
    now: datetime | None = None,
) -> dict[str, int | str]:
    """Apply deterministic lifecycle transitions to all campaigns.

    Args:
        repo:  An EventRepository instance (or any object that exposes
               transition_active_to_dormant and transition_dormant_to_historical).
               The caller owns the session and commit boundary.
        now:   Evaluation timestamp. Defaults to datetime.now(UTC).
               Provide a fixed value in tests for deterministic assertions.

    Returns:
        {
            "active_to_dormant":    <int — campaigns transitioned>,
            "dormant_to_historical": <int — campaigns transitioned>,
            "evaluated_at":         <ISO-8601 string>,
        }
    """
    if now is None:
        now = datetime.now(UTC)

    now_str = now.isoformat()
    active_cutoff = (now - timedelta(days=CAMPAIGN_ACTIVE_DAYS)).isoformat()
    historical_cutoff = (now - timedelta(days=CAMPAIGN_DORMANT_DAYS)).isoformat()

    to_dormant = repo.transition_active_to_dormant(
        last_seen_cutoff=active_cutoff,
        dormant_since=now_str,
        updated_at=now_str,
    )
    to_historical = repo.transition_dormant_to_historical(
        dormant_since_cutoff=historical_cutoff,
        updated_at=now_str,
    )

    return {
        "active_to_dormant": to_dormant,
        "dormant_to_historical": to_historical,
        "evaluated_at": now_str,
    }
