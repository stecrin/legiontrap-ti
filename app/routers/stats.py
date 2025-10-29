import os
import pathlib

from fastapi import APIRouter, Depends, Header, HTTPException, status

router = APIRouter()


def _events_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("EVENTS_PATH", "storage/events.jsonl"))


def verify_api_key(x_api_key: str | None = Header(default=None)):
    expected = (
        os.environ.get("API_KEY")
        or os.environ.get("LEGION_API_KEY")
        or os.environ.get("APP_API_KEY")
        or "dev-123"
    )
    if x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")
    return True


@router.get("/api/stats", dependencies=[Depends(verify_api_key)])
def get_stats():
    """Count lines in EVENTS_PATH (tiny health-ish stat)."""
    p = _events_path()
    total = 0
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            for _ in f:
                total += 1
    # Provide both shapes for compatibility:
    # - legacy: {"events": N}
    # - new:    {"counts": {"total": N}}
    return {"events": total, "counts": {"total": total}}
