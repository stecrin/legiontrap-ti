"""
Standard intelligence export endpoints for LegionTrap TI.

GET /api/exports/attack-navigator  — ATT&CK Navigator layer JSON
GET /api/exports/stix              — STIX 2.1 Indicator bundle JSON

Both endpoints require API key or JWT authentication.
The STIX endpoint is blocked when PRIVACY_MODE is enabled because STIX
Indicator patterns embed raw IP addresses, which privacy mode is designed
to prevent from leaving the system.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository
from app.exports.attack_navigator import build_navigator_layer
from app.exports.stix import build_stix_bundle
from app.utils.auth import require_jwt_or_api_key

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/attack-navigator")
def get_attack_navigator_layer(
    layer_name: str = Query(default="LegionTrap TI", max_length=100),
    _: dict = Depends(require_jwt_or_api_key),
) -> JSONResponse:
    """
    Return an ATT&CK Navigator layer JSON with technique coverage weighted
    by observed event counts.

    Technique IDs and tactic mappings are sourced exclusively from the
    event_types table — no technique IDs are hardcoded in application code.
    PRIVACY_MODE does not affect this endpoint: no IP data is exported.
    """
    with get_session() as session:
        techniques = EventRepository(session).get_attack_technique_counts()
    layer = build_navigator_layer(techniques, layer_name=layer_name)
    return JSONResponse(content=layer)


@router.get("/stix")
def get_stix_bundle(
    limit: int = Query(default=100, ge=1, le=1000),
    min_event_count: int = Query(default=1, ge=1),
    _: dict = Depends(require_jwt_or_api_key),
) -> JSONResponse:
    """
    Return a STIX 2.1 bundle of Indicators, Campaign SDOs, and Relationship SDOs.

    For each eligible IP: one IPv4-Addr SCO + one Indicator SDO.
    For each active/dormant/reactivated campaign: one Campaign SDO.
    For each exported IP that is a campaign member: one Relationship SDO
      (indicator indicates campaign).

    Object IDs are deterministic: the same IP or campaign always produces
    the same ID regardless of when the bundle is generated.

    Blocked when PRIVACY_MODE is enabled. STIX Indicator patterns require
    raw IP addresses; privacy mode masks IPs before export. Use the IOC
    export endpoints (/api/iocs/pf.conf, /api/iocs/ufw.txt) for
    privacy-aware firewall block list generation.
    """
    if settings.PRIVACY_MODE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "STIX export is unavailable when PRIVACY_MODE is enabled. "
                "STIX Indicator patterns require raw IP addresses, which are "
                "masked in privacy mode. Disable PRIVACY_MODE to use this "
                "endpoint, or use /api/iocs/pf.conf and /api/iocs/ufw.txt "
                "for privacy-aware firewall block list exports."
            ),
        )
    with get_session() as session:
        repo = EventRepository(session)
        ips = repo.get_stix_indicator_ips(limit=limit, min_event_count=min_event_count)
        campaigns = repo.get_campaigns_for_export()
        ip_campaign_map = repo.get_campaign_member_ip_map()
    bundle = build_stix_bundle(ips, campaigns=campaigns, ip_campaign_map=ip_campaign_map)
    return JSONResponse(content=bundle)
