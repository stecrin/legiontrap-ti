"""Actor profile CRUD and campaign-linking endpoints — Phase 7 Group B1/B2.

POST   /api/actors                              — create actor profile (201)
GET    /api/actors                              — list actor profiles
POST   /api/actors/{id}/campaigns               — link campaign to actor (201)
GET    /api/actors/{id}/campaigns               — list actor's linked campaigns
DELETE /api/actors/{id}/campaigns/{lineage_id}  — remove a lineage record (204)
GET    /api/actors/{id}                         — get actor profile (404 if not found)
PATCH  /api/actors/{id}                         — partial update actor profile

All endpoints require API key or JWT authentication via require_jwt_or_api_key.
No SQL belongs here — all queries go through EventRepository.

Invariants:
  - No automatic actor attribution.
  - No AI involvement.
  - All actor records and lineage records are created by explicit operator action only.
  - relationship_type vocabulary is enforced by actor_constants.VALID_RELATIONSHIP_TYPES.
  - Duplicate (actor_id, campaign_id) pairs return 409 Conflict.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.intelligence.actor_constants import VALID_ACTOR_STATUSES, VALID_RELATIONSHIP_TYPES
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


class LinkCampaignRequest(BaseModel):
    campaign_id: str
    relationship_type: str
    confidence: float = 0.5
    evidence: str | None = None

    @field_validator("campaign_id")
    @classmethod
    def campaign_id_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("campaign_id must not be blank")
        return v

    @field_validator("relationship_type")
    @classmethod
    def relationship_type_valid(cls, v: str) -> str:
        if v not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid relationship_type {v!r}. "
                f"Must be one of: {sorted(VALID_RELATIONSHIP_TYPES)}"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


@router.post("/{actor_id}/campaigns", status_code=status.HTTP_201_CREATED)
def link_campaign(
    actor_id: str,
    body: LinkCampaignRequest,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Link a campaign to an actor profile.

    Validation order: actor exists → campaign exists → relationship_type in
    VALID_RELATIONSHIP_TYPES (validated by Pydantic) → duplicate check.

    Returns 409 Conflict when the same (actor_id, campaign_id) pair already
    exists.  The operator can delete the existing link and re-create it with a
    corrected relationship_type.

    No automatic attribution.  No AI involvement.  All links are operator-created.
    """
    with get_session() as session:
        repo = EventRepository(session)

        if repo.get_actor_profile(actor_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Actor {actor_id!r} not found",
            )
        if repo.get_campaign(body.campaign_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {body.campaign_id!r} not found",
            )

        existing = repo.find_duplicate_lineage(actor_id, body.campaign_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        f"Campaign {body.campaign_id!r} is already linked to actor {actor_id!r}"
                    ),
                    "existing_lineage_id": existing["id"],
                },
            )

        lineage = repo.link_campaign_to_actor(
            actor_profile_id=actor_id,
            campaign_id=body.campaign_id,
            relationship_type=body.relationship_type,
            confidence=body.confidence,
            evidence_json=body.evidence,
        )
    return lineage


@router.get("/{actor_id}/campaigns")
def list_actor_campaigns(
    actor_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return campaigns linked to this actor, enriched with campaign metadata.

    Each item includes the full lineage record (relationship_type, confidence,
    evidence_json, created_at) plus campaign name, status, last_seen,
    member_ip_count, and has_fingerprint.  404 if actor not found.
    """
    with get_session() as session:
        repo = EventRepository(session)
        if repo.get_actor_profile(actor_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Actor {actor_id!r} not found",
            )
        items = repo.list_actor_campaigns_with_metadata(actor_id, limit=limit)
    return {"items": items, "count": len(items)}


@router.delete("/{actor_id}/campaigns/{lineage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_actor_campaign_link(
    actor_id: str,
    lineage_id: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Remove a campaign-to-actor lineage record.

    Hard-deletes the lineage row only.  The campaign and actor profile are
    not modified.  The original clustering decision is not modified.

    Returns 204 on success.  Returns 404 if the lineage_id does not exist or
    does not belong to actor_id.
    """
    with get_session() as session:
        repo = EventRepository(session)
        record = repo.get_lineage_record(lineage_id)
        if record is None or record["actor_profile_id"] != actor_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lineage record {lineage_id!r} not found for actor {actor_id!r}",
            )
        repo.delete_lineage_record(lineage_id)


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
