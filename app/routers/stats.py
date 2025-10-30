import os

from fastapi import APIRouter, Header, HTTPException

from . import iocs_pf

router = APIRouter()


@router.get("/api/stats")
def get_stats(x_api_key: str | None = Header(default=None, alias="x-api-key")):
    expected = os.getenv("API_KEY") or "dev-123"
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")

    total = 0
    uniq = set()
    for ev in iocs_pf.iter_events():
        total += 1
        ip = ev.get("src_ip")
        if ip:
            uniq.add(ip)

    return {
        "counts": {"total": total, "unique_ips": len(uniq), "last_24h": 0},
        "total_events": total,
        "unique_ips": len(uniq),
        "last_24h": 0,
    }
