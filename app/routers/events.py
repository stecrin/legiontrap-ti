import json
import os
from pathlib import Path as _Path

from fastapi import APIRouter, Header, HTTPException, status

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def get_events(
    limit: int = 10,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    """Return last N events from storage/events.jsonl (reverse order)."""
    api_key = os.environ.get("API_KEY")
    if x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    # Resolve project root: app/routers -> app -> project root
    root = _Path(__file__).resolve().parents[1].parent
    path = root / "storage" / "events.jsonl"
    if not path.exists():
        return {"items": []}

    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    items = [json.loads(line) for line in lines[-limit:]][::-1]  # newest first
    return {"items": items}
