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
    """Extract IPv4 strings from various shapes:
    - direct string values on common keys
    - nested dicts with {ip|addr|address|host}
    - any string content via regex fallback
    """
    found: list[str] = []

    if isinstance(obj, dict):
        # 1) Preferred keys (flat / nested)
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
                # regex scan of JSON for that value (covers deeper nesting)
                with suppress(Exception):
                    found.extend(IPV4_RE.findall(json.dumps(v)))

        # 2) message/log-like fields
        for msg_key in ("message", "msg", "log", "event", "raw"):
            v = obj.get(msg_key)
            if isinstance(v, str):
                found.extend(IPV4_RE.findall(v))

        # 3) Fallback: scan entire event JSON
        with suppress(Exception):
            found.extend(IPV4_RE.findall(json.dumps(obj)))

    elif isinstance(obj, str):
        found.extend(IPV4_RE.findall(obj))

    return found


def unique_attacker_ips(events_path: pathlib.Path) -> list[str]:
    seen: set[str] = set()
    ips: list[str] = []
    for ev in iter_events(events_path):
        for ip in _extract_from_obj(ev):
            if ip not in seen:
                seen.add(ip)
                ips.append(ip)
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
