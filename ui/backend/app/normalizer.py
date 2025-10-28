import uuid
from datetime import UTC, datetime
from typing import Any


def _base(event: dict[str, Any]) -> dict[str, Any]:
    """Wrap an event with id/ts defaults."""
    return {
        "id": event.get("id") or str(uuid.uuid4()),
        "ts": event.get("ts") or datetime.now(UTC).isoformat(),
        "source": event.get("source", "unknown"),
        "type": event.get("type", "generic"),
        "data": event.get("data", {}),
    }


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize heterogeneous sensor payloads (cowrie, opencanary, generic).
    Returns a minimal, consistent schema:
      { id, ts, source, type, data:{ ip?, username? ... } }
    """
    src = (raw.get("source") or "").lower()
    etype = (raw.get("type") or "").lower()
    data = raw.get("data") or raw  # allow flat payloads

    # --- Cowrie ---
    # Example raw (flat):
    #   {"source":"cowrie","eventid":"cowrie.login.failed",
    #    "username":"root","password":"toor","src_ip":"1.2.3.4"}
    eventid = (raw.get("eventid") or "").lower()
    if src == "cowrie" or "cowrie" in eventid:
        username = data.get("username") or raw.get("username")
        password = data.get("password") or raw.get("password")
        ip = data.get("ip") or data.get("src_ip") or raw.get("src_ip")
        if not etype:
            if "login.failed" in eventid:
                etype = "auth_failed"
            elif "login.success" in eventid:
                etype = "auth_success"
            else:
                etype = "cowrie_event"
        norm = {
            "source": "cowrie",
            "type": etype,
            "data": {"username": username, "password": password, "ip": ip},
        }
        return _base(norm)

    # --- OpenCanary ---
    node_id = str(raw.get("node_id") or "")
    if src == "opencanary" or node_id.startswith("opencanary"):
        ip = data.get("src_host") or data.get("remote_addr") or data.get("ip")
        username = data.get("username") or data.get("user")
        etype = etype or str(data.get("logtype") or "canary_event")
        norm = {
            "source": "opencanary",
            "type": etype,
            "data": {"ip": ip, "username": username},
        }
        return _base(norm)

    # --- Generic fallback ---
    ip = data.get("ip") or data.get("src_ip") or data.get("remote_addr")
    username = data.get("username") or data.get("user")
    norm = {
        "source": raw.get("source", "unknown"),
        "type": etype or str(raw.get("event") or raw.get("eventid") or "generic"),
        "data": {"ip": ip, "username": username},
    }
    return _base(norm)
