"""
ASN enrichment utility for LegionTrap TI.

Provides ASN (Autonomous System Number) context for public IPv4 addresses
using a local GeoLite2-ASN.mmdb file. The database file is never committed
to the repository (storage/ is gitignored) and must be provisioned by each
operator alongside GeoLite2-City.mmdb.

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

ASN_DB_PATH = Path("storage/GeoLite2-ASN.mmdb")

_asn_reader: geoip2.database.Reader | None = None
_reader_lock = threading.Lock()


def _get_reader() -> geoip2.database.Reader | None:
    """Return the module-level singleton ASN reader, initializing on first call.

    Returns None if the mmdb file is absent or fails to open. Subsequent calls
    after a failed init re-check the file each time — the operator may provision
    the file after startup without restarting the application.
    """
    global _asn_reader
    if _asn_reader is not None:
        return _asn_reader
    with _reader_lock:
        if _asn_reader is not None:
            return _asn_reader
        if not ASN_DB_PATH.exists():
            return None
        try:
            _asn_reader = geoip2.database.Reader(str(ASN_DB_PATH))
        except Exception:
            return None
    return _asn_reader


def reset_asn_reader_for_testing() -> None:
    """Close and clear the cached reader. Call from test fixtures only."""
    global _asn_reader
    with _reader_lock:
        if _asn_reader is not None:
            with contextlib.suppress(Exception):
                _asn_reader.close()
            _asn_reader = None


def enrich_asn(ip: str) -> dict[str, int | str | None]:
    """Return ASN context for a public IPv4 address.

    Keys: asn (int or None), asn_org (str or None). All values are None when
    the mmdb is absent, the IP is not in the database, or any error occurs.
    Never raises.
    """
    reader = _get_reader()
    if reader is None:
        return {"asn": None, "asn_org": None}
    try:
        response = reader.asn(ip)
        return {
            "asn": response.autonomous_system_number,
            "asn_org": response.autonomous_system_organization,
        }
    except Exception:
        return {"asn": None, "asn_org": None}
