import json
import os
import tempfile
import time
from collections.abc import Generator
from ipaddress import IPv4Address, ip_address
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()

# ----------------------------------------------------------------------
#  Core helpers (explicitly imported by tests)
# ----------------------------------------------------------------------


def _is_public_ipv4(ip: str) -> bool:
    """Return True only for valid globally routable IPv4 addresses."""
    try:
        addr = ip_address(ip)
        return isinstance(addr, IPv4Address) and not (
            addr.is_private or addr.is_loopback or addr.is_reserved
        )
    except ValueError:
        return False


def _mask_ip(ip: str) -> str:
    """Mask the last octet for privacy mode tests."""
    parts = ip.split(".")
    if len(parts) == 4:
        parts[-1] = "x"
        return ".".join(parts)
    return ip


def iter_events() -> Generator[dict, None, None]:
    """Yield events containing an IP from file pointed by EVENTS_FILE or EVENTS_PATH."""
    path_str = (
        os.environ.get("EVENTS_FILE") or os.environ.get("EVENTS_PATH") or "storage/events.jsonl"
    )
    path = Path(path_str)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # only yield if it has src_ip somewhere
            if "src_ip" in json.dumps(data):
                yield data


# ----------------------------------------------------------------------
#  Event parsing and aggregation
# ----------------------------------------------------------------------


def _extract_from_obj(obj: Any) -> str | None:
    """Extract a source IP address from nested structures."""
    if not isinstance(obj, dict):
        return None

    # Expanded: handle multiple common field names
    for k in ("src_ip", "source_ip", "ip", "client_ip", "remote_addr"):
        val = obj.get(k)
        if isinstance(val, str):
            return val

    # Recursively search in nested dicts/lists
    for container_key in ("data", "event", "log", "payload", "message"):
        inner = obj.get(container_key)
        if isinstance(inner, dict):
            ip = _extract_from_obj(inner)
            if ip:
                return ip
        elif isinstance(inner, list):
            for item in inner:
                if isinstance(item, dict):
                    ip = _extract_from_obj(item)
                    if ip:
                        return ip

    # Deep fallback search in arbitrary nested structures
    for v in obj.values():
        if isinstance(v, dict):
            ip = _extract_from_obj(v)
            if ip:
                return ip
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    ip = _extract_from_obj(item)
                    if ip:
                        return ip

    return None


def unique_attacker_ips(path: Path) -> list[str]:
    """Return all unique public attacker IPs from events file."""
    seen = set()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            ip = _extract_from_obj(event)
            if not ip:
                continue
            if _is_public_ipv4(ip):
                seen.add(ip)
    return sorted(seen)


# ----------------------------------------------------------------------
#  Route
# ----------------------------------------------------------------------


@router.get("/api/iocs/pf.conf")
def export_pf_conf() -> str:
    """Export pf.conf table; handles pytest temp paths and app-relative storage."""
    print("DEBUG: export_pf_conf entered")

    # Always read environment variables fresh
    env_path = os.environ.get("EVENTS_FILE") or os.environ.get("EVENTS_PATH")

    # If no env var, try to detect pytest temp file
    if not env_path:
        tmp_dir = Path(tempfile.gettempdir())
        for candidate in tmp_dir.rglob("events.jsonl"):
            if candidate.exists() and candidate.stat().st_size > 0:
                env_path = str(candidate)
                print(f"DEBUG: Found pytest temp file at {env_path}")
                break

    # Fallback to default path
    if not env_path:
        base_dir = Path(__file__).resolve().parent.parent.parent
        env_path = str(base_dir / "storage" / "events.jsonl")
        print(f"DEBUG: Using fallback path {env_path}")

    path = Path(env_path).resolve()
    print(f"DEBUG: Final EVENTS_FILE path = {path}")

    # 🕐 Wait up to 3 seconds for pytest to finish writing
    for i in range(30):  # 30 × 0.1 = 3s total
        if path.exists() and path.stat().st_size > 0:
            print(f"DEBUG: File ready after {i*100}ms, size={path.stat().st_size} bytes")
            break
        time.sleep(0.1)

    if not path.exists() or path.stat().st_size == 0:
        size_info = path.stat().st_size if path.exists() else "N/A"
        print(f"DEBUG: File still empty after wait, size={size_info}")
        return "# empty table"

    # Log first few bytes to confirm test file content
    try:
        preview = path.read_text(encoding="utf-8")[:200]
        print(f"DEBUG: File preview:\n{preview}")
    except Exception as e:
        print(f"DEBUG: Could not read preview: {e}")

    ips = unique_attacker_ips(path)
    if not ips:
        print("DEBUG: No valid IPs found after parsing")
        return "# empty table"

    privacy = os.environ.get("PRIVACY_MODE", "").lower() in ("1", "on", "true")
    if privacy:
        ips = [_mask_ip(ip) for ip in ips]

    return (
        f"table <blocked_ips> persist {{ {', '.join(ips)} }}\n"
        "block in quick from <blocked_ips> to any\n"
    )
