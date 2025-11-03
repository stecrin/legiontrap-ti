import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import PlainTextResponse

from ui.backend.app.enrichment.manager import EnrichmentManager

from .normalizer import normalize_event
from .notifier import notify

enricher = EnrichmentManager()

app = FastAPI(title="LegionTrap TI API", version="0.3.0")

# --- rotation/retention knobs ---
ROTATE_MAX_BYTES = int(os.getenv("ROTATE_MAX_BYTES", "1000000"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "14"))
EVENTS_PATH = Path(os.getenv("EVENTS_PATH", "storage/events.jsonl"))
EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)

API_KEY = os.getenv("API_KEY")


def _api_key_check(x_api_key: str | None):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _secure_dep(x_api_key: str | None = Header(default=None)):
    _api_key_check(x_api_key)


def _ensure_storage():
    if not EVENTS_PATH.exists():
        EVENTS_PATH.touch()


def _read_all_events() -> list[dict[str, Any]]:
    _ensure_storage()
    events: list[dict[str, Any]] = []
    with EVENTS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _append_event(evt: dict[str, Any]) -> dict[str, Any]:
    _ensure_storage()
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evt) + "\n")
    return evt


# ---------------------- ROUTES ----------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/ingest", dependencies=[Depends(_secure_dep)])
def ingest(payload: dict[str, Any] = Body(...), background_tasks: BackgroundTasks = None):
    """Accepts raw payloads, normalizes, enriches, stores, and triggers notifier."""
    evt = normalize_event(payload)

    # 🔍 Enrichment integration
    enrichment = enricher.enrich(evt)
    if enrichment:
        evt["enrichment"] = enrichment

    saved = _append_event(evt)
    if background_tasks is not None:
        background_tasks.add_task(notify, saved)
    return {"status": "ok", "enriched": saved}


@app.get("/api/events", dependencies=[Depends(_secure_dep)])
def list_events():
    return _read_all_events()


@app.get("/api/events/paged", dependencies=[Depends(_secure_dep)])
def list_events_paged(limit: int = Query(100, ge=1, le=1000), after_ts: str | None = None):
    evts = _read_all_events()
    if after_ts:
        cutoff = datetime.fromisoformat(after_ts.replace("Z", "+00:00"))
        evts = [
            e
            for e in evts
            if datetime.fromisoformat(
                e.get("ts", datetime.now(UTC).isoformat()).replace("Z", "+00:00")
            )
            > cutoff
        ]
    return evts[-limit:]


@app.get("/api/stats", dependencies=[Depends(_secure_dep)])
def stats():
    evts = _read_all_events()
    by_source = Counter(e.get("source", "unknown") for e in evts)
    by_type = Counter(e.get("type", "generic") for e in evts)
    return {"counts": {"total": len(evts), "by_source": dict(by_source), "by_type": dict(by_type)}}


@app.get("/api/iocs.json", dependencies=[Depends(_secure_dep)])
def ioc_feed():
    events = _read_all_events()
    ips, domains = [], []
    for e in events:
        d = e.get("data") or {}
        ip, dom = d.get("ip"), d.get("domain")
        if ip and ip not in ips:
            ips.append(ip)
        if dom and dom not in domains:
            domains.append(dom)
    return {"ips": ips, "domains": domains, "generated": datetime.now(UTC).isoformat()}


@app.get("/api/config", dependencies=[Depends(_secure_dep)])
def get_config():
    return {
        "privacy_mode": os.getenv("PRIVACY_MODE", "off"),
        "events_path": str(EVENTS_PATH),
        "rotate_max_bytes": ROTATE_MAX_BYTES,
        "retention_days": RETENTION_DAYS,
        "api_key_set": bool(API_KEY),
    }


@app.post("/api/test")
async def test_endpoint(request: Request):
    data = await request.json()
    print("[TEST] got data:", data)
    return {"echo": data}


@app.get("/api/iocs/ufw.txt")
async def iocs_ufw_txt():
    import json
    import os
    from pathlib import Path

    events_path = Path(os.getenv("EVENTS_PATH", "storage/events.jsonl"))
    seen, ips = set(), []
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                evt = json.loads(line)
            except Exception:
                continue
            ip = ((evt.get("data") or {}).get("ip")) or None
            if ip and ip not in seen:
                seen.add(ip)
                ips.append(ip)
    body = "\n".join(f"deny from {ip}" for ip in ips)
    if body:
        body += "\n"
    return PlainTextResponse(body)


@app.get("/api/iocs/pf.conf")
async def iocs_pf_conf():
    import json
    import os
    from pathlib import Path

    from fastapi.responses import PlainTextResponse

    events_path = Path(os.getenv("EVENTS_PATH", "storage/events.jsonl"))
    ips = set()
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            try:
                evt = json.loads(line)
                ip = (evt.get("data") or {}).get("ip")
                if ip:
                    ips.add(ip)
            except Exception:
                continue
    ip_list = ", ".join(sorted(ips))
    body = (
        f"table <blocked_ips> persist {{ {ip_list} }}\nblock in quick from <blocked_ips> to any\n"
    )
    return PlainTextResponse(body)
