"""Behavioral drift alert endpoints — Phase 7 Group A.

GET  /api/alerts                    — list alerts (unacknowledged by default)
POST /api/alerts/{id}/acknowledge   — acknowledge an alert
GET  /api/campaigns/{id}/alerts     — alerts for a specific campaign

All endpoints require API key or JWT authentication via require_jwt_or_api_key.
No SQL belongs here — all queries go through EventRepository.

Alerts are informational only.  Acknowledgement records operator awareness;
it does not modify campaigns, fingerprints, or clustering decisions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(tags=["alerts"])


class AcknowledgeRequest(BaseModel):
    notes: str | None = None


@router.get("/api/alerts")
def list_alerts(
    campaign_id: str | None = Query(default=None),
    include_acknowledged: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return behavioral drift alerts, newest first.

    By default returns only unacknowledged alerts.
    Pass include_acknowledged=true to include all alerts.
    Optionally filter to a single campaign via campaign_id.
    """
    with get_session() as session:
        items = EventRepository(session).list_alerts(
            campaign_id=campaign_id,
            include_acknowledged=include_acknowledged,
            limit=limit,
        )
    return {"items": items, "count": len(items)}


@router.post("/api/alerts/{alert_id}/acknowledge", status_code=status.HTTP_200_OK)
def acknowledge_alert(
    alert_id: str,
    body: AcknowledgeRequest,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Mark a behavioral alert as acknowledged.

    Acknowledgement closes the deduplication gate for this (campaign, dimension)
    pair — a new alert can fire once the same condition is detected again.
    The acknowledgement notes field is optional free text.
    """
    with get_session() as session:
        repo = EventRepository(session)
        alert = repo.get_alert(alert_id)
        if alert is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id!r} not found",
            )
        updated = repo.acknowledge_alert(alert_id, notes=body.notes)
    return updated


@router.get("/api/campaigns/{campaign_id}/alerts")
def get_campaign_alerts(
    campaign_id: str,
    include_acknowledged: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return all alerts for a specific campaign (acknowledged and unacknowledged by default).

    Pass include_acknowledged=false to return only unacknowledged alerts.
    """
    with get_session() as session:
        repo = EventRepository(session)
        if repo.get_campaign(campaign_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Campaign {campaign_id!r} not found",
            )
        items = repo.list_alerts(
            campaign_id=campaign_id,
            include_acknowledged=include_acknowledged,
            limit=limit,
        )
    return {"items": items, "count": len(items)}
