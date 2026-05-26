"""Admin endpoints for operator-triggered maintenance operations.

All endpoints require API key authentication only (not JWT). This prevents
dashboard sessions from triggering maintenance operations accidentally.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.intelligence.analytics import refresh_all_campaign_analytics
from app.intelligence.lifecycle import run_lifecycle_transitions
from app.utils.auth import require_api_key

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/run-lifecycle-job")
def run_lifecycle_job(
    _: dict = Depends(require_api_key),
) -> dict:
    """Trigger campaign lifecycle transitions immediately.

    Moves active/reactivated campaigns to dormant when last_seen exceeds
    CAMPAIGN_ACTIVE_DAYS, and dormant campaigns to historical when dormant_since
    exceeds CAMPAIGN_DORMANT_DAYS. Returns the count of each transition.

    This is the same logic that runs on the daily maintenance schedule.
    Safe to call repeatedly — transitions are idempotent.
    """
    with get_session() as session:
        repo = EventRepository(session)
        result = run_lifecycle_transitions(repo)
    return result


@router.post("/run-analytics-job")
def run_analytics_job(
    _: dict = Depends(require_api_key),
) -> dict:
    """Recompute campaign analytics for all campaigns.

    Populates attack_tactic_dist and top_target_ports on every campaigns row
    by aggregating events from each campaign's member IPs. Results are stored
    as JSON in the existing nullable columns.

    Safe to call repeatedly — computation is idempotent.
    """
    with get_session() as session:
        repo = EventRepository(session)
        result = refresh_all_campaign_analytics(repo)
    return result
