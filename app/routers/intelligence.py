"""
Intelligence query endpoints for LegionTrap TI.

GET /api/intelligence/ips       — paginated source IP list, ranked by score
GET /api/intelligence/ips/{ip}  — single IP intelligence profile

All endpoints require API key or JWT authentication via require_jwt_or_api_key.
No SQL belongs here — all queries go through EventRepository.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.connection import get_session
from app.db.repository import EventRepository
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/ips")
def list_intelligence_ips(
    limit: int = Query(default=100, ge=1, le=1000),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return source IP intelligence records sorted by reputation_score DESC, event_count DESC."""
    with get_session() as session:
        items = EventRepository(session).list_source_ips(limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/ips/{ip}")
def get_intelligence_ip(
    ip: str,
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return the intelligence profile for a single source IP. 404 if not found."""
    with get_session() as session:
        item = EventRepository(session).get_source_ip(ip)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IP {ip!r} not found",
        )
    return item


@router.get("/top-countries")
def get_top_countries(
    limit: int = Query(default=10, ge=1, le=100),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return top countries by total event_count aggregated from source_ips."""
    with get_session() as session:
        items = EventRepository(session).get_top_countries(limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/top-asns")
def get_top_asns(
    limit: int = Query(default=10, ge=1, le=100),
    _: dict = Depends(require_jwt_or_api_key),
):
    """Return top ASNs by total event_count aggregated from source_ips."""
    with get_session() as session:
        items = EventRepository(session).get_top_asns(limit=limit)
    return {"items": items, "count": len(items)}
