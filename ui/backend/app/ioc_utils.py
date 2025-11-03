# ui/backend/app/ioc_utils.py
from __future__ import annotations

import hashlib
import ipaddress
from collections.abc import Iterable

# Import the module (not the object) so tests that reload config work
from .core import config


def unique_ordered(items: Iterable[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _salted_hash(text: str) -> str:
    settings = config.settings  # pull fresh settings every call
    blob = (settings.FEED_SALT + "::" + text).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def _anonymize_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return value  # not an IP, let domain anonymizer handle it
    return f"ip-{_salted_hash(str(ip))}"


def _anonymize_domain(value: str) -> str:
    v = value.strip().lower()
    parts = v.split(".")
    if len(parts) >= 2:
        tld = parts[-1]
        return f"host-{_salted_hash(v)}.{tld}"
    return f"host-{_salted_hash(v)}"


def maybe_privacy_map(value: str) -> str:
    """
    If PRIVACY_MODE is true -> map to salted pseudonyms.
    Else return the original.
    """
    s = config.settings  # dynamic read (respects test reloads)
    if not s.PRIVACY_MODE:
        return value

    try:
        ipaddress.ip_address(value)
        return _anonymize_ip(value)
    except ValueError:
        return _anonymize_domain(value)
