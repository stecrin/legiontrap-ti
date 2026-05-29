"""Campaign intelligence endpoints.

GET  /api/campaigns                                           — paginated list with evidence_quality
GET  /api/campaigns/sparse        — sparse campaign list with density metrics
GET  /api/campaigns/uncertain-associations                    — pending review queue
POST /api/campaigns/uncertain-associations/{id}/review        — submit analyst review
GET  /api/campaigns/{campaign_id}                             — campaign detail
GET  /api/campaigns/{campaign_id}/observations                — observation list
GET  /api/campaigns/{campaign_id}/weight-profile              — per-campaign weight profile
GET  /api/campaigns/{campaign_id}/density                     — full campaign density metrics

All endpoints require API key or JWT authentication via require_jwt_or_api_key.
No SQL belongs here — all queries go through EventRepository.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.config import settings as _settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.intelligence.campaign_density import (
    _DENSITY_ESTABLISHED_THRESHOLD,
    _DENSITY_MATURE_THRESHOLD,
    compute_campaign_density,
)
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
    """Return campaigns sorted by last_seen DESC with evidence_quality annotation."""
    with get_session() as session:
        repo = EventRepository(session)
        items = repo.list_campaigns_with_fingerprint_status(limit=limit)
        if items:
            cids = [c["id"] for c in items]
            obs_counts = repo.get_bulk_observation_counts(cids)
        else:
            obs_counts = {}

    for item in items:
        counts = obs_counts.get(item["id"], {"observation_count": 0, "review_count": 0})
        density = compute_campaign_density(
            campaign=item,
            observation_count=counts["observation_count"],
            review_count=counts["review_count"],
        )
        item["evidence_quality"] = density.classification
        item["density_score"] = density.density_score

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


@router.get("/sparse")
def list_sparse_campaigns(
    limit: int = Query(default=200, ge=1, le=1000),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return campaigns with no representative fingerprint, newest first.

    These campaigns lack sufficient behavioral data for the analytics pipeline
    to produce reliable clustering or stability outputs.  They are surfaced
    read-only so operators can identify campaigns that need more events or
    are candidates for archival.

    Each item includes full density metrics so operators understand why the
    campaign is sparse.
    """
    with get_session() as session:
        repo = EventRepository(session)
        items = repo.list_sparse_campaigns(limit=limit)
        if items:
            cids = [c["id"] for c in items]
            obs_counts = repo.get_bulk_observation_counts(cids)
        else:
            obs_counts = {}

    for item in items:
        counts = obs_counts.get(item["id"], {"observation_count": 0, "review_count": 0})
        density = compute_campaign_density(
            campaign=item,
            observation_count=counts["observation_count"],
            review_count=counts["review_count"],
        )
        item["observation_count"] = density.observation_count
        item["review_count"] = density.review_count
        item["age_span_hours"] = density.age_span_hours
        item["density_score"] = density.density_score
        item["evidence_quality"] = density.classification

    return {
        "items": items,
        "count": len(items),
        "sparse_criteria": "representative_fingerprint_json IS NULL",
    }


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


@router.get("/{campaign_id}/density")
def get_campaign_density(
    campaign_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return full evidence quality and density metrics for a campaign.

    Density score [0.0, 1.0] is a weighted combination of four normalised
    sub-scores: observation count, unique source IPs, campaign age span, and
    analyst review count.  Classification is one of:
      sparse      — no representative fingerprint
      emerging    — fingerprint present, density < 0.35
      established — density in [0.35, 0.70)
      mature      — density >= 0.70

    Read-only.  No campaign mutations.
    """
    with get_session() as session:
        repo = EventRepository(session)
        campaign = repo.get_campaign_with_fingerprint(campaign_id)
        if campaign is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id!r} not found",
            )
        counts = repo.get_campaign_observation_counts(campaign_id)

    density = compute_campaign_density(
        campaign=campaign,
        observation_count=counts["observation_count"],
        review_count=counts["review_count"],
    )

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign["name"],
        "has_fingerprint": density.has_fingerprint,
        "observation_count": density.observation_count,
        "unique_ip_count": density.unique_ip_count,
        "review_count": density.review_count,
        "age_span_hours": density.age_span_hours,
        "density_score": density.density_score,
        "evidence_quality": density.classification,
        "density_components": {
            "obs_score": density.components.obs_score,
            "ip_score": density.components.ip_score,
            "age_score": density.components.age_score,
            "review_score": density.components.review_score,
        },
        "thresholds": {
            "obs_mature": _settings.SPARSE_OBS_MATURE,
            "obs_established": _settings.SPARSE_OBS_ESTABLISHED,
            "ip_mature": _settings.SPARSE_IP_MATURE,
            "age_hours_mature": _settings.SPARSE_AGE_HOURS_MATURE,
            "age_hours_established": _settings.SPARSE_AGE_HOURS_ESTABLISHED,
            "density_mature": _DENSITY_MATURE_THRESHOLD,
            "density_established": _DENSITY_ESTABLISHED_THRESHOLD,
        },
    }
