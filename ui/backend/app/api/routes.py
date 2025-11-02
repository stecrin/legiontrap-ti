import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from app.enrichment.manager import EnrichmentManager

router = APIRouter()
enricher = EnrichmentManager()


@router.post("/api/ingest")
async def ingest_event(request: Request):
    """
    Ingest endpoint — normalizes + enriches incoming honeypot events.
    Example payload:
      {"src_ip": "8.8.8.8", "event_type": "cowrie.login"}
    """
    try:
        payload = await request.json()
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from err

    # Normalize / fill event
    event = {
        "id": str(uuid.uuid4()),
        "ts": datetime.utcnow().isoformat(),
        "source": payload.get("source", "unknown"),
        "type": payload.get("event_type", "generic"),
        "data": {
            "username": payload.get("username"),
            "password": payload.get("password"),
            "ip": payload.get("src_ip"),
        },
    }

    # 🔍 Enrichment step
    enriched = enricher.enrich(event)
    event["enrichment"] = enriched

    return {"status": "ok", "enriched": event}
