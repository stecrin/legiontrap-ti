import ipaddress
import json
import os
import pathlib
import re

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

POSSIBLE_KEYS = ("src_ip", "source_ip", "remote_addr")
NESTED_SUBKEYS = ("src_ip", "source_ip", "remote_addr")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _is_public_ipv4(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.version == 4 and not (
            ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_multicast
        )
    except Exception:
        return False


def _mask_ip(ip: str) -> str:
    parts = ip.split(".")
    if len(parts) == 4:
        parts[-1] = "x"
        return ".".join(parts)
    return ip


def _extract_from_obj(obj) -> str | None:
    # Flat
    if isinstance(obj, dict):
        for k in POSSIBLE_KEYS:
            if k in obj and isinstance(obj[k], str):
                v = obj[k]
                return v if _is_public_ipv4(v) else None
        # Nested under "data"
        data = obj.get("data")
        if isinstance(data, dict):
            for k in NESTED_SUBKEYS:
                v = data.get(k)
                if isinstance(v, str):
                    return v if _is_public_ipv4(v) else None

    # Generic scan of any strings present
    def walk(x):
        if isinstance(x, dict):
            for vv in x.values():
                out = walk(vv)
                if out:
                    return out
        elif isinstance(x, list | tuple | set):
            for vv in x:
                out = walk(vv)
                if out:
                    return out
        elif isinstance(x, str):
            for cand in IPV4_RE.findall(x):
                if _is_public_ipv4(cand):
                    return cand
        return None

    return walk(obj)


def _resolve_events_path(lines_path: pathlib.Path | None) -> pathlib.Path | None:
    if lines_path:
        return pathlib.Path(lines_path)
    env_file = os.getenv("EVENTS_FILE")
    if env_file:
        return pathlib.Path(env_file)
    env_path = os.getenv("EVENTS_PATH")
    if env_path:
        return pathlib.Path(env_path)
    p = pathlib.Path("storage/events.jsonl")
    return p if p.exists() else None


def iter_events(lines_path: pathlib.Path | None = None):
    path = _resolve_events_path(lines_path)
    if not path or not path.exists():
        return
        yield  # pragma: no cover

    privacy_on = os.getenv("PRIVACY_MODE", "off").lower() == "on"
    with path.open("r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            ip = _extract_from_obj(obj)
            if not ip:
                continue
            obj["src_ip"] = _mask_ip(ip) if privacy_on else ip
            yield obj


def unique_attacker_ips(lines_path: pathlib.Path | None = None) -> list[str]:
    """
    Collect unique *public* attacker IPv4s by scanning the events file text.
    Respects PRIVACY_MODE ("on"/"off") by masking the last octet when on.
    """
    path = _resolve_events_path(lines_path)
    if not path or not path.exists():
        return []
    privacy_on = os.getenv("PRIVACY_MODE", "off").lower() == "on"
    text = path.read_text(errors="ignore")
    candidates = set(IPV4_RE.findall(text))
    out: set[str] = set()
    for ip in candidates:
        if _is_public_ipv4(ip):
            out.add(_mask_ip(ip) if privacy_on else ip)
    return sorted(out)


@router.get("/api/iocs/ufw.txt", response_class=PlainTextResponse)
def iocs_ufw_txt() -> str:
    ips = unique_attacker_ips()
    if not ips:
        return ""
    return "\n".join(f"deny from {ip}" for ip in ips) + "\n"


@router.get("/api/iocs/pf.conf", response_class=PlainTextResponse)
def iocs_pf_conf() -> str:
    ips = unique_attacker_ips()
    ip_list = ", ".join(ips)
    return (
        f"table <blocked_ips> persist {{ {ip_list} }}\nblock in quick from <blocked_ips> to any\n"
    )


# --- strict override: only accept explicit keys, not generic 'ip' ---
def _extract_from_obj(obj) -> None | str:
    if not isinstance(obj, dict):
        return None

    # flat keys only
    for k in ("src_ip", "source_ip", "remote_addr"):
        v = obj.get(k)
        if isinstance(v, str) and _is_public_ipv4(v):
            return v

    # nested under 'data'
    data = obj.get("data")
    if isinstance(data, dict):
        for k in ("src_ip", "source_ip", "remote_addr"):
            v = data.get(k)
            if isinstance(v, str) and _is_public_ipv4(v):
                return v

    return None
