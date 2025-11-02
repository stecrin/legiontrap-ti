"""
Normalizer module
-----------------
Takes raw event data, ensures consistent schema, and enriches with metadata (GeoIP, etc.)
"""

import asyncio

from ui.backend.app.enrichment.manager import EnrichmentManager


class EventNormalizer:
    """Handles normalization and enrichment of incoming events."""

    def __init__(self):
        self.enricher = EnrichmentManager()

    async def normalize_and_enrich_async(self, raw_event: dict) -> dict:
        """Normalize incoming event and enrich with GeoIP metadata."""
        event = {}

        # --- Basic normalization ---
        # Normalize key structure
        if "data" in raw_event:
            data = raw_event["data"]
            event["src_ip"] = data.get("ip") or data.get("src_ip")
            event["username"] = data.get("username")
            event["password"] = data.get("password")
        else:
            # Fallback if data is already flat
            event["src_ip"] = raw_event.get("ip") or raw_event.get("src_ip")

        event["source"] = raw_event.get("source", "unknown")
        event["type"] = raw_event.get("type", "generic")

        # --- Enrichment phase ---
        try:
            enriched = await self.enricher.enrich_ip({"ip": event.get("src_ip")})
            event["enrichment"] = enriched
        except Exception as e:
            event["enrichment_error"] = str(e)

        return event

    def normalize_and_enrich(self, raw_event: dict) -> dict:
        """Sync wrapper (for FastAPI routes or CLI ingestion)."""
        return asyncio.run(self.normalize_and_enrich_async(raw_event))
