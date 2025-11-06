import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status

router = APIRouter()


@router.get("/api/stats")
def get_stats(x_api_key: str | None = Header(default=None, alias="x-api-key")):
    """Return live stats from storage/events.jsonl."""

    api_key = "dev-123"
    if x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    path = Path("storage/events.jsonl")
    total = 0
    seen_ips = set()
    last_24h = 0

    if path.exists():
        for line in path.read_text().splitlines():
            total += 1
            try:
                obj = json.loads(line)
                ip = (
                    obj.get("ip")
                    or obj.get("src_ip")
                    or obj.get("dst_ip")
                    or obj.get("client_ip")
                    or obj.get("source_ip")
                )
                if ip:
                    seen_ips.add(ip)
            except json.JSONDecodeError:
                continue

    return {
        "counts": {
            "total": total,
            "unique_ips": len(seen_ips),
            "last_24h": last_24h,
        },
        "total_events": total,
        "unique_ips": len(seen_ips),
        "last_24h": last_24h,
    }
