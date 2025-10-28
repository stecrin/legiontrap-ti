# LegionTrap API — event ingestion, stats, IOC export
# Author: Stefan Cringusi
# Date: 2025-10-28
# Context: Secured all routes with API key (except /api/health), added /api/stats,
#          IOC exports for ufw/pf, and log rotation/retention toggled via env.
import json
import os
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
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
)
from fastapi.responses import PlainTextResponse

from .normalizer import normalize_event
from .notifier import notify
from .storage import prune_old_files, roll_files_if_needed

# --- rotation/retention knobs from env ---
ROTATE_MAX_BYTES = int(os.getenv("ROTATE_MAX_BYTES", "1000000"))
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "14"))


app = FastAPI(title="LegionTrap TI API", version="0.2.0")

EVENTS_PATH = Path(os.getenv("EVENTS_PATH", "/data/events.jsonl"))
if isinstance(EVENTS_PATH, str):
    EVENTS_PATH = Path(EVENTS_PATH)


def _ensure_storage():
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
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


API_KEY = os.getenv("API_KEY")


def _api_key_check(x_api_key: str | None):
    # rotate & prune before append
    try:
        roll_files_if_needed(EVENTS_PATH, ROTATE_MAX_BYTES)
        prune_old_files(EVENTS_PATH, RETENTION_DAYS)
    except Exception:
        pass
    # If API_KEY is set, require matching header
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _secure_dep(x_api_key: str | None = Header(default=None)):
    _api_key_check(x_api_key)


def _within(dt_iso: str, window: timedelta) -> bool:
    try:
        dt_iso = (dt_iso or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_iso)
        return dt >= datetime.now(UTC) - window
    except Exception:
        return False


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/events", dependencies=[Depends(_secure_dep)])
def list_events() -> list[dict[str, Any]]:
    return _read_all_events()


@app.post("/api/events", dependencies=[Depends(_secure_dep)])
def create_event(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    evt = {
        "id": payload.get("id") or str(uuid.uuid4()),
        "ts": payload.get("ts") or datetime.now(UTC).isoformat(),
        "source": payload.get("source", "unknown"),
        "type": payload.get("type", "generic"),
        "data": payload.get("data", {}),
    }
    return _append_event(evt)


@app.get("/api/iocs.json", dependencies=[Depends(_secure_dep)])
def ioc_feed() -> dict[str, Any]:
    events = _read_all_events()
    ips: list[str] = []
    domains: list[str] = []
    for e in events:
        d = e.get("data") or {}
        ip = d.get("ip")
        dom = d.get("domain")
        if ip and ip not in ips:
            ips.append(ip)
        if dom and dom not in domains:
            domains.append(dom)
    return {"ips": ips, "domains": domains, "generated": datetime.now(UTC).isoformat()}


@app.post("/api/ingest", dependencies=[Depends(_secure_dep)])
def ingest(payload: dict[str, Any] = Body(...), background_tasks: BackgroundTasks = None):
    """Accepts raw sensor payloads, normalizes, stores, and triggers best-effort alert."""
    evt = normalize_event(payload)
    saved = _append_event(evt)
    if background_tasks is not None:
        background_tasks.add_task(notify, saved)
    return {"status": "ingested", "event": saved}


API_KEY = os.getenv("API_KEY")


def _api_key_check(x_api_key: str | None):
    # If API_KEY is set in env, require matching header; if not set, allow
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _parse_ts(ts: str):
    try:
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.now(UTC)


@app.get("/api/events/paged", dependencies=[Depends(_secure_dep)])
def list_events_paged(
    limit: int = Query(100, ge=1, le=1000),
    after_ts: str | None = None,
    x_api_key: str | None = Header(default=None),
):
    _api_key_check(x_api_key)
    evts = _read_all_events()
    if after_ts:
        cutoff = _parse_ts(after_ts)
        if cutoff:
            # Keep only events with ts > cutoff
            out = []
            for e in evts:
                ts = e.get("ts")
                if not ts:
                    continue
                dt = _parse_ts(ts)
                if dt and dt > cutoff:
                    out.append(e)
            evts = out
    # return newest 'limit' items
    return evts[-limit:]


@app.get("/api/stats", dependencies=[Depends(_secure_dep)])
def stats() -> dict[str, Any]:
    evts = _read_all_events()
    by_source = Counter(e.get("source", "unknown") for e in evts)
    by_type = Counter(e.get("type", "generic") for e in evts)

    last24 = [e for e in evts if _within(e.get("ts", ""), timedelta(hours=24))]
    last7 = [e for e in evts if _within(e.get("ts", ""), timedelta(days=7))]

    return {
        "counts": {
            "total": len(evts),
            "last_24h": len(last24),
            "last_7d": len(last7),
            "by_source": dict(by_source),
            "by_type": dict(by_type),
        }
    }


def _collect_ips():
    evts = _read_all_events()
    seen, out = set(), []
    for e in evts:
        ip = ((e.get("data") or {}).get("ip")) or None
        if ip and ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out


@app.get("/api/iocs/ufw.txt", response_class=PlainTextResponse, dependencies=[Depends(_secure_dep)])
def iocs_ufw():
    lines = [f"deny from {ip}" for ip in _collect_ips()]
    return "\n".join(lines) + ("\n" if lines else "")


@app.get("/api/iocs/pf.conf", response_class=PlainTextResponse, dependencies=[Depends(_secure_dep)])
def iocs_pf():
    ips = _collect_ips()
    body = ", ".join(ips) if ips else ""
    return f"table <blocked_ips> persist {{ {body} }}\nblock in quick from <blocked_ips> to any\n"


@app.get("/api/config", dependencies=[Depends(_secure_dep)])
def get_config() -> dict[str, Any]:
    return {
        "privacy_mode": os.getenv("PRIVACY_MODE", "off"),
        "events_path": str(EVENTS_PATH),
        "rotate_max_bytes": ROTATE_MAX_BYTES,
        "retention_days": RETENTION_DAYS,
        "api_key_set": bool(os.getenv("API_KEY")),
    }
