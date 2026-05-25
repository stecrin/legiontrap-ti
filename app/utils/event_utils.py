"""
Event normalization utilities for the LegionTrap TI ingestion pipeline.

All normalization logic lives here. No FastAPI, SQLAlchemy, or router imports.
Called by Stage 3 of the ingestion pipeline (app/routers/ingest.py, Phase 2).
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# IP extraction
# ---------------------------------------------------------------------------

# Priority order from INGESTION_PIPELINE.md — Cowrie nested path first.
_CANDIDATE_FIELDS: list[tuple[str, ...]] = [
    ("data", "ip"),
    ("data", "src_ip"),
    ("src_ip",),
    ("ip",),
    ("client_ip",),
    ("source_ip",),
]


def _is_public_ipv4(value: str) -> bool:
    """Return True if value is a syntactically valid, public, non-reserved IPv4 address."""
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    if addr.version != 4:
        return False
    return (
        not addr.is_private
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_reserved
        and not addr.is_multicast
        and not addr.is_unspecified
    )


def extract_src_ip(event_dict: dict[str, Any]) -> str | None:
    """
    Extract a valid public IPv4 from an event dict using the documented priority order.

    Returns None if no valid public IP is found — this is not a rejection condition.
    Depth is bounded to exactly two levels (one nested dict); no unbounded recursion.
    """
    for path in _CANDIDATE_FIELDS:
        if len(path) == 1:
            value = event_dict.get(path[0])
        else:
            # Exactly two levels — no unbounded recursion.
            container = event_dict.get(path[0])
            if not isinstance(container, dict):
                continue
            value = container.get(path[1])

        if isinstance(value, str) and _is_public_ipv4(value):
            return value

    return None


# ---------------------------------------------------------------------------
# Event type normalisation
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, dict[str, str]] = {
    "cowrie": {
        "cowrie.login.failed": "auth_failed",
        "cowrie.login.success": "auth_success",
        "cowrie.command.input": "command_exec",
        "cowrie.session.file_upload": "malware_upload",
    },
    "dionaea": {
        "dionaea.connection.free": "port_scan",
    },
}


def normalize_event_type(raw_type: str, source: str) -> str:
    """
    Map sensor-specific event type strings to canonical event_types.id values.

    Unmapped types are lowercased with dots replaced by underscores and stored
    as-is — they can be re-mapped later by updating the event_types table.
    """
    return _TYPE_MAP.get(source, {}).get(raw_type, raw_type.lower().replace(".", "_"))


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


def parse_timestamp(ts_value: Any) -> datetime | None:
    """
    Parse a timestamp in ISO8601 format (with or without timezone) or Unix epoch.

    Returns a timezone-aware UTC datetime, or None if unparseable.
    A None return causes the event to be rejected — ts is required.
    """
    if ts_value is None:
        return None

    # Unix epoch (int or float)
    if isinstance(ts_value, int | float):
        try:
            return datetime.fromtimestamp(ts_value, tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None

    try:
        # Replace trailing Z with +00:00 for fromisoformat compatibility (Python < 3.11)
        dt = datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        return None
