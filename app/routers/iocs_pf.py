# LegionTrap TI — IOC Exporter (PF, UFW)
#
# Exports attacker IPs from the SQLite events table into firewall-compatible
# formats (UFW and PF). Privacy mode hashes IPs before export.

import hashlib
import os

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import PlainTextResponse, Response

from app.core.config import settings
from app.db.connection import get_session
from app.db.repository import EventRepository


def require_api_key(x_api_key: str | None = Header(default=None)):
    """Reject requests without or with the wrong API key."""
    api_key = os.environ.get("API_KEY")
    if api_key and x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return True


router = APIRouter()


def _get_ips() -> list[str]:
    with get_session() as session:
        return EventRepository(session).get_unique_public_ips()


@router.get("/ufw.txt", dependencies=[Depends(require_api_key)])
def export_ufw_txt() -> Response:
    """
    Export a UFW-compatible deny list.

    When PRIVACY_MODE=on, IPs are anonymized using FEED_SALT.
    Falls back to ["1.2.3.4"] when no events have been ingested.
    """
    ips = _get_ips()
    if not ips:
        ips = ["1.2.3.4"]

    privacy = os.environ.get("PRIVACY_MODE", "").lower() in ("1", "on", "true")
    if privacy:
        salt = settings.FEED_SALT

        def _anon(i: str) -> str:
            return "ip-" + hashlib.sha256((salt + "::" + i).encode()).hexdigest()[:12]

        ips = [_anon(i) for i in ips]

    body = "\n".join(f"deny from {ip}" for ip in ips) + "\n"
    return PlainTextResponse(body)


@router.get("/pf.conf", dependencies=[Depends(require_api_key)])
def export_pf_conf() -> Response:
    """
    Export a PF firewall table configuration.

    When PRIVACY_MODE=on, IPs are anonymized using FEED_SALT.
    Falls back to ["1.2.3.4"] when no events have been ingested.
    """
    ips = _get_ips()
    if not ips:
        ips = ["1.2.3.4"]

    privacy = os.environ.get("PRIVACY_MODE", "").lower() in ("1", "on", "true")
    if privacy:
        salt = settings.FEED_SALT

        def _anon(i: str) -> str:
            return "ip-" + hashlib.sha256((salt + "::" + i).encode()).hexdigest()[:12]

        ips = [_anon(i) for i in ips]

    ip_list = ", ".join(sorted(ips))
    body = (
        f"table <blocked_ips> persist {{ {ip_list} }}\n"
        f"block in quick from <blocked_ips> to any\n"
    )
    return PlainTextResponse(body)
