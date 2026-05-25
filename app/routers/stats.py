import os

from fastapi import APIRouter, Header, HTTPException, status

from app.db.connection import get_session
from app.db.repository import EventRepository

router = APIRouter()


@router.get("/api/stats")
def get_stats(x_api_key: str | None = Header(default=None, alias="x-api-key")):
    """Return live aggregate stats from the events table."""
    api_key = os.environ.get("API_KEY")
    if x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    with get_session() as session:
        stats = EventRepository(session).get_stats()

    # Preserve the existing response contract: both a nested "counts" dict
    # (checked by test_stats_with_key) and flat top-level keys.
    return {
        "counts": {
            "total": stats["total_events"],
            "unique_ips": stats["unique_ips"],
            "last_24h": stats["last_24h"],
        },
        "total_events": stats["total_events"],
        "unique_ips": stats["unique_ips"],
        "last_24h": stats["last_24h"],
    }
