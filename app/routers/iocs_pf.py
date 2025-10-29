import ipaddress
import json
import os
import pathlib
import re
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PRIVACY_MODE = os.environ.get("PRIVACY_MODE", "").lower() in {"1", "true", "on", "yes"}


def _events_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("EVENTS_PATH", "storage/events.jsonl"))


def iter_events(lines_path: pathlib.Path):
    if not lines_path.exists():
        return
    with lines_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            with suppress(json.JSONDecodeError):
                yield json.loads(line)


POSSIBLE_KEYS: tuple[str, ...] = (
    "src_ip",
    "source_ip",
    "ip",
    "client_ip",
    "remote_ip",
    "dst_ip",
    "attacker_ip",
    "peer_ip",
    "host",
    "address",
    "addr",
    "src",
    "source",
    "remote",
    "client",
    "peer",
    "attacker",
)
NESTED_SUBKEYS: tuple[str, ...] = ("ip", "addr", "address", "host")


def _extract_from_obj(obj: Any) -> Iterable[str]:
    """Extract IPv4 strings from various shapes."""
    found: list[str] = []

    if isinstance(obj, dict):
        for k in POSSIBLE_KEYS:
            if k in obj:
                v = obj[k]
                if isinstance(v, str):
                    found.extend(IPV4_RE.findall(v))
                elif isinstance(v, dict):
                    for sub in NESTED_SUBKEYS:
                        sub_v = v.get(sub)
                        if isinstance(sub_v, str):
                            found.extend(IPV4_RE.findall(sub_v))
                with suppress(Exception):
                    found.extend(IPV4_RE.findall(json.dumps(v)))

        for msg_key in ("message", "msg", "log", "event", "raw"):
            v = obj.get(msg_key)
            if isinstance(v, str):
                found.extend(IPV4_RE.findall(v))

        with suppress(Exception):
            found.extend(IPV4_RE.findall(json.dumps(obj)))

    elif isinstance(obj, str):
        found.extend(IPV4_RE.findall(obj))

    return found


def _is_public_ipv4(ip: str) -> bool:
    """True if ip is a globally routable IPv4 address."""
    try:
        ip4 = ipaddress.IPv4Address(ip)
        return ip4.is_global  # excludes private, reserved, multicast, loopback, link-local, etc.
    except ipaddress.AddressValueError:
        return False


def _mask_ip(ip: str) -> str:
    """Privacy mode: mask last octet."""
    try:
        ipaddress.IPv4Address(ip)
        parts = ip.split(".")
        parts[-1] = "x"
        return ".".join(parts)
    except ipaddress.AddressValueError:
        return ip


def unique_attacker_ips(events_path: pathlib.Path) -> list[str]:
    seen: set[str] = set()
    ips: list[str] = []
    for ev in iter_events(events_path):
        for ip in _extract_from_obj(ev):
            if not _is_public_ipv4(ip):
                continue
            out = _mask_ip(ip) if PRIVACY_MODE else ip
            if out not in seen:
                seen.add(out)
                ips.append(out)
    return ips


@router.get(
    "/api/iocs/pf.conf",
    response_class=PlainTextResponse,
    summary="pf.conf snippet with attacker IPs",
)
def get_pf_conf():
    events_path = _events_path()
    ips = unique_attacker_ips(events_path)
    table_name = "block_in_log"
    ip_block = ",\n  ".join(ips) if ips else ""
    snippet = (
        f"table <{table_name}> persist {{\n"
        f"  {ip_block}\n"
        f"}}\n\n"
        f"# Example rule:\n"
        f"block in log quick from <{table_name}> to any\n"
    )
    return snippet
