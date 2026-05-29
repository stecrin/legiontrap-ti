"""Actor profile CRUD, suggestion, and stability endpoints — Phase 7 B1/B3/B4.

POST   /api/actors                   — create actor profile (201)
GET    /api/actors                   — list actor profiles
GET    /api/actors/suggestions       — candidate campaign pairs (read-only)
GET    /api/actors/{id}              — get actor profile detail (404 if not found)
GET    /api/actors/{id}/stability    — aggregated stability view (read-only)
PATCH  /api/actors/{id}              — partial update (display_name, notes, confidence, status)

All endpoints require API key or JWT authentication via require_jwt_or_api_key.
No SQL belongs here — all queries go through EventRepository.

Invariants:
  - No automatic actor attribution.
  - No AI involvement.
  - All actor records are created by explicit operator action only.
  - relationship_type vocabulary is enforced by actor_constants.VALID_RELATIONSHIP_TYPES.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator

from app.core.config import settings as _settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.intelligence.actor_constants import VALID_ACTOR_STATUSES
from app.intelligence.actor_stability import aggregate_actor_stability
from app.intelligence.actor_suggestions import build_actor_suggestions
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(prefix="/api/actors", tags=["actors"])


class ActorCreateRequest(BaseModel):
    display_name: str
    notes: str | None = None
    confidence: float = 0.5
    status: str = "active"

    @field_validator("display_name")
    @classmethod
    def display_name_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("display_name must not be blank")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in VALID_ACTOR_STATUSES:
            raise ValueError(
                f"Invalid status {v!r}. Must be one of: {sorted(VALID_ACTOR_STATUSES)}"
            )
        return v


class ActorPatchRequest(BaseModel):
    display_name: str | None = None
    notes: str | None = None
    confidence: float | None = None
    status: str | None = None

    @field_validator("display_name")
    @classmethod
    def display_name_nonempty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("display_name must not be blank")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ACTOR_STATUSES:
            raise ValueError(
                f"Invalid status {v!r}. Must be one of: {sorted(VALID_ACTOR_STATUSES)}"
            )
        return v


@router.post("", status_code=status.HTTP_201_CREATED)
def create_actor(
    body: ActorCreateRequest,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Create a new actor profile.

    All fields are operator-supplied.  No automatic attribution, no AI
    involvement, no auto-generated display names.
    """
    with get_session() as session:
        actor = EventRepository(session).create_actor_profile(
            display_name=body.display_name,
            notes=body.notes,
            confidence=body.confidence,
            status=body.status,
        )
    return actor


@router.get("")
def list_actors(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return actor profiles ordered by created_at DESC.

    Optionally filter by status ('active' or 'archived').
    """
    if status is not None and status not in VALID_ACTOR_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(f"Invalid status {status!r}. Must be one of: {sorted(VALID_ACTOR_STATUSES)}"),
        )
    with get_session() as session:
        items = EventRepository(session).list_actor_profiles(status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/suggestions")
def get_actor_suggestions(
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int | None = Query(default=None, ge=1, le=100),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return candidate campaign pairs for actor attribution review.

    Compares representative fingerprints of active/dormant/reactivated
    campaigns pairwise.  Pairs already co-attributed to the same actor
    via campaign_lineage are excluded.

    Results are sorted by similarity_score DESC and capped at limit.
    suggested_relationship_type is advisory only — it is never written
    to any table automatically.  Campaigns without a representative
    fingerprint are excluded from comparison.

    Read-only.  No writes to actor_profiles, campaign_lineage, or campaigns.
    """
    effective_min_score = (
        min_score if min_score is not None else _settings.ACTOR_SUGGESTION_MIN_SCORE
    )
    effective_limit = limit if limit is not None else _settings.ACTOR_SUGGESTION_LIMIT

    with get_session() as session:
        repo = EventRepository(session)
        campaigns = repo.list_campaigns_for_suggestions()
        coattributed_pairs = repo.get_coattributed_campaign_pairs()

    suggestions, total_evaluated = build_actor_suggestions(
        campaigns,
        coattributed_pairs,
        min_score=effective_min_score,
        limit=effective_limit,
    )

    return {
        "suggestions": suggestions,
        "count": len(suggestions),
        "total_pairs_evaluated": total_evaluated,
        "min_score_applied": effective_min_score,
        "campaigns_evaluated": len(campaigns),
    }


@router.get("/{actor_id}")
def get_actor(
    actor_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return a single actor profile. 404 if not found."""
    with get_session() as session:
        actor = EventRepository(session).get_actor_profile(actor_id)
    if actor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Actor {actor_id!r} not found",
        )
    return actor


@router.get("/{actor_id}/stability")
def get_actor_stability(
    actor_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return aggregated behavioral stability for campaigns linked to an actor.

    Reads campaign_lineage for the actor, fetches behavioral_stability_json
    from each linked campaign, and aggregates across all contributors.

    Campaigns with NULL behavioral_stability_json or status 'insufficient_data'
    are counted in campaigns_missing_stability but excluded from aggregate scores.
    They still appear in contributors with composite_score=null.

    status values:
      ok                 — all linked campaigns have stability data
      no_linked_campaigns — actor has no campaign_lineage rows
      no_stability_data  — linked campaigns exist but none have stability
      partial_data       — some campaigns have stability, some do not

    Read-only.  No writes to actor_profiles, campaign_lineage, or campaigns.
    404 if the actor does not exist.
    """
    with get_session() as session:
        repo = EventRepository(session)
        actor = repo.get_actor_profile(actor_id)
        if actor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Actor {actor_id!r} not found",
            )
        campaign_rows = repo.list_actor_campaign_stability(actor_id)

    agg = aggregate_actor_stability(campaign_rows)
    return {
        "actor_id": actor_id,
        "actor_display_name": actor["display_name"],
        **agg,
    }


@router.patch("/{actor_id}")
def patch_actor(
    actor_id: str,
    body: ActorPatchRequest,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Partially update an actor profile.

    Accepts any subset of: display_name, notes, confidence, status.
    Permitted status values: 'active', 'archived'.
    Returns the updated row. 404 if actor not found.

    Only fields present in the request body are written.  Omitting a field
    leaves the stored value unchanged.  Sending notes=null clears the notes.
    """
    with get_session() as session:
        repo = EventRepository(session)
        if repo.get_actor_profile(actor_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Actor {actor_id!r} not found",
            )
        explicit = body.model_fields_set
        kwargs: dict = {}
        if "display_name" in explicit:
            kwargs["display_name"] = body.display_name
        if "notes" in explicit:
            kwargs["notes"] = body.notes
        if "confidence" in explicit:
            kwargs["confidence"] = body.confidence
        if "status" in explicit:
            kwargs["status"] = body.status
        updated = repo.update_actor_profile(actor_id, **kwargs)
    return updated
