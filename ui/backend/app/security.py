# ui/backend/app/security.py
import hashlib
import ipaddress

from fastapi import Header, HTTPException, status

# IMPORTANT: import the module, not the object
from .core import config  # access config.settings dynamically on each call


def require_api_key(x_api_key: str | None = Header(default=None)):
    settings = config.settings  # grab the latest instance
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return True


def _salted_hash(text: str) -> str:
    settings = config.settings
    blob = (settings.FEED_SALT + "::" + text).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def anonymize_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return value  # leave as-is if not an IP
    # map to a stable pseudonym
    return f"ip-{_salted_hash(str(ip))}"


def anonymize_domain(value: str) -> str:
    # keep TLD coarse, hash the rest
    parts = value.lower().split(".")
    if len(parts) < 2:
        return f"host-{_salted_hash(value)}"
    tld = parts[-1]
    return f"host-{_salted_hash(value)}.{tld}"
