"""Campaign intelligence endpoints.

GET  /api/campaigns                                           — paginated list
GET  /api/campaigns/uncertain-associations                    — pending review queue
POST /api/campaigns/uncertain-associations/{id}/review        — submit analyst review
GET  /api/campaigns/{campaign_id}                             — campaign detail
GET  /api/campaigns/{campaign_id}/observations                — observation list
GET  /api/campaigns/{campaign_id}/weight-profile              — per-campaign weight profile

All endpoints require API key or JWT authentication via require_jwt_or_api_key.
No SQL belongs here — all queries go through EventRepository.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.utils.auth import require_jwt_or_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

_VALID_REVIEW_DECISIONS = {"analyst_confirmed", "analyst_denied"}


class ObservationReviewRequest(BaseModel):
    decision: str
    notes: str | None = None


@router.get("")
def list_campaigns(
    limit: int = Query(default=100, ge=1, le=1000),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return campaigns sorted by last_seen DESC."""
    with get_session() as session:
        items = EventRepository(session).list_campaigns(limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/uncertain-associations")
def list_uncertain_associations(
    campaign_id: str | None = Query(default=None),
    include_reviewed: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return uncertain-association observations pending analyst review.

    By default only unreviewed (pending) observations are returned.
    Pass include_reviewed=true to include observations that have already
    been reviewed.  Optionally filter to a single campaign via campaign_id.
    """
    with get_session() as session:
        items = EventRepository(session).list_uncertain_observations(
            campaign_id=campaign_id,
            include_reviewed=include_reviewed,
            limit=limit,
        )
    return {"items": items, "count": len(items)}


@router.post("/uncertain-associations/{observation_id}/review", status_code=status.HTTP_200_OK)
def review_uncertain_association(
    observation_id: str,
    body: ObservationReviewRequest,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Submit an analyst review for an uncertain-association observation.

    decision must be one of: analyst_confirmed, analyst_denied.
    The review records the analyst's interpretation only — it does not
    modify the original clustering decision, campaign membership, or
    observation records.
    """
    if body.decision not in _VALID_REVIEW_DECISIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid decision {body.decision!r}. "
                f"Must be one of: {sorted(_VALID_REVIEW_DECISIONS)}"
            ),
        )

    reviewed_at = datetime.now(UTC).isoformat()

    with get_session() as session:
        repo = EventRepository(session)
        obs = repo.get_campaign_observation(observation_id)
        if obs is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Observation {observation_id!r} not found",
            )
        repo.annotate_campaign_observation(
            observation_id=observation_id,
            analyst_decision=body.decision,
            analyst_notes=body.notes,
            reviewed_at=reviewed_at,
        )
        updated = repo.get_campaign_observation(observation_id)

    try:
        with get_session() as audit_session:
            EventRepository(audit_session).insert_audit_log(
                event_type="observation_review",
                detail=json.dumps(
                    {
                        "observation_id": observation_id,
                        "campaign_id": obs["campaign_id"],
                        "decision": body.decision,
                    }
                ),
            )
    except Exception:
        logger.exception(
            "Audit log failed for observation_review observation_id=%s", observation_id
        )

    return updated


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


@router.get("/{campaign_id}/weight-profile")
def get_campaign_weight_profile(
    campaign_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return the per-campaign similarity weight profile.

    When no calibrated profile exists the global default weights are returned
    with status='using_global_defaults'.  The profile is built by the weight
    profile job from analyst review decisions; it is never set automatically.
    """
    from app.core.config import settings as _settings

    global_defaults = {
        "timing": _settings.WEIGHT_TIMING,
        "sequence": _settings.WEIGHT_SEQUENCE,
        "protocol": _settings.WEIGHT_PROTOCOL,
        "credential": _settings.WEIGHT_CREDENTIAL,
        "target": _settings.WEIGHT_TARGET,
    }

    with get_session() as session:
        repo = EventRepository(session)
        if repo.get_campaign(campaign_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id!r} not found",
            )
        profile = repo.get_weight_profile(campaign_id)

    if profile is None:
        return {
            "campaign_id": campaign_id,
            "weights": global_defaults,
            "global_defaults": global_defaults,
            "review_count": 0,
            "confirmed_count": 0,
            "denied_count": 0,
            "adjustment_log": [],
            "computed_at": None,
            "status": "using_global_defaults",
        }

    return {
        **profile,
        "global_defaults": global_defaults,
        "status": "calibrated",
    }
