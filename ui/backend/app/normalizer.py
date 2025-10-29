from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _first(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize raw honeypot payloads into a common schema:
    {
      "id": str(uuid),
      "ts": iso8601,
      "source": "cowrie" | "opencanary" | ...,
      "type": "auth_failed" | "generic",
      "data": {
        "username": str|None,
        "password": str|None,
        "ip": str|None
      }
    }
    """
    source = (raw.get("source") or "unknown").lower()
    eventid = (raw.get("eventid") or "").lower()

    ip = _first(
        raw.get("src_ip"),
        raw.get("remote_host"),
        raw.get("src"),
        raw.get("peer"),
        raw.get("ip"),
    )
    username = _first(raw.get("username"), raw.get("user"), raw.get("login"))
    password = _first(raw.get("password"), raw.get("pass"))

    etype = "generic"

    # Cowrie: failed login
    if (source == "cowrie" and "login.failed" in eventid) or (
        source == "opencanary" and ("login.failed" in eventid or "canary.login.failed" in eventid)
    ):
        etype = "auth_failed"

    normalized = {
        "id": str(uuid.uuid4()),
        "ts": _now_iso(),
        "source": source,
        "type": etype,
        "data": {
            "username": username,
            "password": password,
            "ip": ip,
        },
    }
    return normalized


def normalize_event(raw):
    """Back-compat wrapper expected by main.py."""
    return normalize(raw)
