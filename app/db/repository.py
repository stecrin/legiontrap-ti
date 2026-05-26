"""
EventRepository — the single SQL boundary for LegionTrap TI.

All SQL lives in the app/db/repositories/ sub-modules. This module re-exports
EventRepository so all callers continue to use the same import path:

    from app.db.repository import EventRepository

Internal structure (by concern):
    repositories/write.py        — insert, upsert, update, delete
    repositories/read.py         — dashboard queries and ingest-side cache reads
    repositories/intelligence.py — intelligence API query methods
    repositories/fingerprint.py  — behavioral fingerprint reads and writes
    repositories/campaign.py     — campaign CRUD and clustering query methods

The caller owns the session and therefore the transaction boundary.

Construction pattern (caller controls atomicity):
    with get_session() as session:
        repo = EventRepository(session)
        repo.insert_raw_event(raw)
        repo.insert_event(event)
        repo.upsert_source_ip(event.src_ip, event.ts)
    # session commits on clean exit, rolls back on exception

No FastAPI, router, or application imports belong in the sub-modules.
"""

from __future__ import annotations

from app.db.repositories.campaign import CampaignRepository
from app.db.repositories.fingerprint import FingerprintRepository
from app.db.repositories.intelligence import IntelligenceRepository
from app.db.repositories.read import ReadRepository
from app.db.repositories.write import WriteRepository


class EventRepository(
    WriteRepository,
    ReadRepository,
    IntelligenceRepository,
    FingerprintRepository,
    CampaignRepository,
):
    """
    Unified repository class. Inherits all SQL methods from the five concern
    mixins. Callers see a single object with the full method surface; the
    internal split is an organisation detail invisible to callers.

    Python MRO: EventRepository → WriteRepository → ReadRepository →
                IntelligenceRepository → FingerprintRepository →
                CampaignRepository → RepositoryBase → object
    """
