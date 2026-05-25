import os

from fastapi import APIRouter, Header, HTTPException, status

from app.db.connection import get_session
from app.db.repository import EventRepository

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def get_events(
    limit: int = 10,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    """Return last N events from the events table, newest first."""
    api_key = os.environ.get("API_KEY")
    if x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    with get_session() as session:
        items = EventRepository(session).list_events(limit=limit)
    return {"items": items}
