import asyncio

from ui.backend.app.enrichment.manager import EnrichmentManager


async def main():
    mgr = EnrichmentManager()
    result = await mgr.enrich_ip({"ip": "8.8.8.8"})
    print("✅ Enriched data:", result)


if __name__ == "__main__":
    asyncio.run(main())
