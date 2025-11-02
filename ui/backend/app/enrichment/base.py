# ui/backend/app/enrichment/base.py

from abc import ABC, abstractmethod


class BaseEnricher(ABC):
    """Abstract base class for all enrichment modules (e.g., GeoIP, ASN, Threat feeds)."""

    @abstractmethod
    async def enrich(self, ip: str) -> dict:
        """Return enrichment data for the given IP or domain."""
        pass
