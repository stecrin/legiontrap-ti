import json
from pathlib import Path as _Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def get_events(limit: int = 10):
    """Return last N events from storage/events.jsonl (reverse order)."""
    # Resolve project root: app/routers -> app -> project root
    root = _Path(__file__).resolve().parents[1].parent
    path = root / "storage" / "events.jsonl"
    if not path.exists():
        return {"items": []}

    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    items = [json.loads(line) for line in lines[-limit:]][::-1]  # newest first
    return {"items": items}
