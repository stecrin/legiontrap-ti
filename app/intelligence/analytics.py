"""Campaign analytics population service — deterministic, no AI, no external calls.

Computes attack_tactic_dist and top_target_ports for each campaign by joining
campaign_members → events → event_types.  Results are stored as JSON in the
existing nullable campaign columns.  All computation is idempotent; running
refresh multiple times produces the same result.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.repository import EventRepository


def refresh_campaign_analytics(
    repo: EventRepository,
    campaign_id: str,
    now: datetime | None = None,
) -> dict:
    """Recompute and persist analytics for a single campaign.

    Returns the computed values (useful for inspection/testing).
    """
    if now is None:
        now = datetime.now(UTC)

    tactic_dist = repo.compute_campaign_attack_tactic_dist(campaign_id)
    top_ports = repo.compute_campaign_top_target_ports(campaign_id)

    tactic_json = json.dumps(tactic_dist) if tactic_dist else None
    ports_json = json.dumps(top_ports) if top_ports else None

    repo.update_campaign_analytics(
        campaign_id=campaign_id,
        attack_tactic_dist=tactic_json,
        top_target_ports=ports_json,
        updated_at=now.isoformat(),
    )

    return {
        "campaign_id": campaign_id,
        "attack_tactic_dist": tactic_dist,
        "top_target_ports": top_ports,
    }


def refresh_all_campaign_analytics(
    repo: EventRepository,
    now: datetime | None = None,
) -> dict:
    """Recompute analytics for all campaigns (all statuses).

    Returns the count of campaigns updated and the evaluation timestamp.
    """
    if now is None:
        now = datetime.now(UTC)

    campaign_ids = repo.list_all_campaign_ids()
    for cid in campaign_ids:
        refresh_campaign_analytics(repo, cid, now)

    return {
        "campaigns_updated": len(campaign_ids),
        "refreshed_at": now.isoformat(),
    }
