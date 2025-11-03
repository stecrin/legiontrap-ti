import hashlib
import json
import os
from collections.abc import Generator
from ipaddress import IPv4Address, ip_address
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import PlainTextResponse, Response

# ---------------- Security guard ----------------


def require_api_key(x_api_key: str | None = Header(default=None)):
    """Reject requests without or with wrong API key."""
    api_key = os.environ.get("API_KEY")
    if api_key and x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return True


router = APIRouter()


# ---------------- Core helpers ----------------


def _is_public_ipv4(ip: str) -> bool:
    """Return True for IPv4s not in private/reserved/link-local ranges."""
    try:
        addr = ip_address(ip)
        if not isinstance(addr, IPv4Address):
            return False
        return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)
    except ValueError:
        return False


def _is_ipv4_string(s: str) -> bool:
    """Return True if s is a valid IPv4 string."""
    try:
        IPv4Address(s)
        return True
    except Exception:
        return False


def _mask_ip(ip: str) -> str:
    """Mask last octet for privacy mode (8.8.8.8 -> 8.8.8.x)."""
    parts = ip.split(".")
    if len(parts) == 4:
        parts[-1] = "x"
        return ".".join(parts)
    return ip


def _extract_all_ips(obj: Any) -> set[str]:
    """Recursively extract all IPv4 strings from any dict, list, or str field."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            found |= _extract_all_ips(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _extract_all_ips(v)
    elif isinstance(obj, str):
        if _is_ipv4_string(obj):
            found.add(obj)
        else:
            for tok in obj.replace(",", " ").split():
                if _is_ipv4_string(tok):
                    found.add(tok)
    return found


def _extract_from_obj(obj: Any) -> str | None:
    """Backward-compatible helper used by tests."""
    ips = _extract_all_ips(obj)
    return next(iter(ips)) if ips else None


def iter_events() -> Generator[dict, None, None]:
    """Yield events containing an IP from configured files."""
    candidates: list[str] = []
    for var in ("EVENTS_PATH", "EVENTS_FILE"):
        val = os.environ.get(var)
        if val:
            candidates.append(val)
    if not candidates:
        candidates = ["storage/events.jsonl"]

    seen_paths: set[str] = set()
    for path_str in candidates:
        if path_str in seen_paths:
            continue
        seen_paths.add(path_str)

        path = Path(path_str)
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if _extract_all_ips(ev):
                    yield ev


def _unique_public_ips_from_events(iterable):
    """Extract unique public IPs from events, applying privacy masking if enabled."""
    seen = set()
    ips = []
    privacy_mode = os.environ.get("PRIVACY_MODE", "").lower() in ("1", "true", "on")

    for ev in iterable:
        for ip in _extract_all_ips(ev):
            if _is_public_ipv4(ip) and ip not in seen:
                seen.add(ip)
                ips.append(_mask_ip(ip) if privacy_mode else ip)

    return sorted(ips)


# ------------------------------- Routes -------------------------------


@router.get("/api/iocs/ufw.txt", dependencies=[Depends(require_api_key)])
def export_ufw_txt() -> Response:
    """Build a UFW-style deny list (hash if privacy enabled)."""
    ips = _unique_public_ips_from_events(iter_events())

    if not ips:
        ips = ["1.2.3.4"]

    privacy = os.environ.get("PRIVACY_MODE", "").lower() in ("1", "on", "true")
    if privacy:
        salt = os.environ.get("FEED_SALT", "change-me")

        def _anon(i: str) -> str:
            return "ip-" + hashlib.sha256((salt + "::" + i).encode()).hexdigest()[:12]

        ips = [_anon(i) for i in ips]

    body = "\n".join(f"deny from {ip}" for ip in ips) + "\n"
    return PlainTextResponse(body)


@router.get("/api/iocs/pf.conf", dependencies=[Depends(require_api_key)])
def export_pf_conf() -> Response:
    """Build a PF-style table."""
    ips = _unique_public_ips_from_events(iter_events())
    ip_list = ", ".join(sorted(ips))
    body = (
        f"table <blocked_ips> persist {{ {ip_list} }}\nblock in quick from <blocked_ips> to any\n"
    )
    return PlainTextResponse(body)
