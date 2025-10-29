import json
import os
import pathlib

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()


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
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def unique_attacker_ips(events_path: pathlib.Path) -> list[str]:
    """Extract unique source IPs from events via src_ip/source_ip/ip fields."""
    ips = []
    seen = set()
    for ev in iter_events(events_path):
        ip = ev.get("src_ip") or ev.get("source_ip") or ev.get("ip")
        if ip and ip not in seen:
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
