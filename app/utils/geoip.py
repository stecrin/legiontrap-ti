"""
GeoIP enrichment utility for LegionTrap TI.

Provides geographic context for public IPv4 addresses using a local
GeoLite2-City.mmdb file. The database file is never committed to the
repository (storage/ is gitignored) and must be provisioned by each
operator. See docs/PHASE_2_BLUEPRINT.md Section 5 for provisioning steps.

Enrichment is best-effort: any failure (missing file, IP not in database,
reader error) returns a dict of all-None values without raising. The ingest
pipeline must never fail because of an enrichment error.

No FastAPI, SQLAlchemy, or router imports belong in this module.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path

import geoip2.database

CITY_DB_PATH = Path("storage/GeoLite2-City.mmdb")

_city_reader: geoip2.database.Reader | None = None
_reader_lock = threading.Lock()


def _get_reader() -> geoip2.database.Reader | None:
    """Return the module-level singleton City reader, initializing on first call.

    Returns None if the mmdb file is absent or fails to open. Subsequent calls
    after a failed init re-check the file each time — the operator may provision
    the file after startup without restarting the application.
    """
    global _city_reader
    if _city_reader is not None:
        return _city_reader
    with _reader_lock:
        if _city_reader is not None:
            return _city_reader
        if not CITY_DB_PATH.exists():
            return None
        try:
            _city_reader = geoip2.database.Reader(str(CITY_DB_PATH))
        except Exception:
            return None
    return _city_reader


def reset_reader_for_testing() -> None:
    """Close and clear the cached reader. Call from test fixtures only."""
    global _city_reader
    with _reader_lock:
        if _city_reader is not None:
            with contextlib.suppress(Exception):
                _city_reader.close()
            _city_reader = None


def enrich_ip(ip: str) -> dict[str, str | None]:
    """Return geographic context for a public IPv4 address.

    Keys: country_code, country_name, city. All values are None when the
    mmdb is absent, the IP is not in the database, or any error occurs.
    Never raises.
    """
    reader = _get_reader()
    if reader is None:
        return {"country_code": None, "country_name": None, "city": None}
    try:
        response = reader.city(ip)
        return {
            "country_code": response.country.iso_code,
            "country_name": response.country.name,
            "city": response.city.name,
        }
    except Exception:
        return {"country_code": None, "country_name": None, "city": None}
