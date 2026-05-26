"""Campaign intelligence endpoints.

GET /api/campaigns                          — paginated campaign list
GET /api/campaigns/{campaign_id}            — detail: campaign + members + observations
GET /api/campaigns/{campaign_id}/observations — observation list for one campaign

All endpoints require API key or JWT authentication via require_jwt_or_api_key.
No SQL belongs here — all queries go through EventRepository.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("")
def list_campaigns(
    limit: int = Query(default=100, ge=1, le=1000),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return campaigns sorted by last_seen DESC."""
    with get_session() as session:
        items = EventRepository(session).list_campaigns(limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return campaign detail with members and observations. 404 if not found."""
    with get_session() as session:
        repo = EventRepository(session)
        campaign = repo.get_campaign(campaign_id)
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id!r} not found",
            )
        members = repo.get_campaign_members(campaign_id)
        observations = repo.get_campaign_observations(campaign_id)
    return {
        **campaign,
        "members": members,
        "observations": observations,
    }


@router.get("/{campaign_id}/observations")
def get_campaign_observations(
    campaign_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return observations for a campaign ordered by observed_at ASC. 404 if not found."""
    with get_session() as session:
        repo = EventRepository(session)
        if repo.get_campaign(campaign_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id!r} not found",
            )
        observations = repo.get_campaign_observations(campaign_id)
    return {"items": observations, "count": len(observations)}
