"""
Enrichment Manager — safely performs GeoIP lookups.
Handles missing DB gracefully (no blocking or network calls).
"""

import logging

from ui.backend.app.enrichment.geoip import GeoIP

log = logging.getLogger(__name__)


class _EnrichmentManagerOld:
    def __init__(self):
        self._geoip = None  # Lazy init

    def _get_geoip(self):
        if self._geoip is None:
            try:
                self._geoip = GeoIP()
                log.info("GeoIP reader initialized")
            except Exception as e:
                log.warning(f"GeoIP init failed: {e}")
                self._geoip = None
        return self._geoip

    def enrich(self, event: dict):
        """Attach geo info if available."""
        ip = event.get("src_ip") or (event.get("data") or {}).get("ip")
        if not ip:
            return {}

        geoip = self._get_geoip()
        if not geoip:
            return {}

        try:
            geo = geoip.lookup(ip)
            return {"geo": geo}
        except Exception as e:
            log.warning(f"GeoIP lookup failed for {ip}: {e}")
            return {}


class EnrichmentManager:
    def __init__(self):
        print("[ENRICH] init manager")  # <-- add
        self._geoip = None

    def _get_geoip(self):
        print("[ENRICH] get_geoip called")  # <-- add
        if self._geoip is None:
            try:
                self._geoip = GeoIP()
                print("[ENRICH] GeoIP created")
            except Exception as e:
                print("[ENRICH] GeoIP init failed", e)
                self._geoip = None
        return self._geoip

    def enrich(self, event: dict):
        print("[ENRICH] enrich() called")  # <-- add
        ip = event.get("src_ip") or (event.get("data") or {}).get("ip")
        print(f"[ENRICH] IP = {ip}")
        if not ip:
            return {}
        geoip = self._get_geoip()
        if not geoip:
            print("[ENRICH] No geoip instance")
            return {}
        try:
            geo = geoip.lookup(ip)
            print("[ENRICH] lookup finished", geo)
            return {"geo": geo}
        except Exception as e:
            print("[ENRICH] lookup failed", e)
            return {}
