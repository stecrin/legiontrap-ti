"""
Canonical Pydantic schemas for the LegionTrap TI event pipeline.

Layer boundaries:
  RawEvent        — input validation boundary (sensor wire format, any source)
  HoneypotEvent   — post-normalization canonical form (written to DB)
  EnrichedEvent   — HoneypotEvent + GeoIP context (Phase 3, added at ingest)
  IngestRequest   — POST /api/ingest request body wrapper
  IngestError     — per-event failure record in ingest receipts
  IngestReceipt   — POST /api/ingest response

No FastAPI, SQLAlchemy, or router imports belong in this module.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RawEvent(BaseModel):
    """
    Sensor wire format — the event exactly as received before normalization.

    extra="allow" is intentional: sensors evolve and add new fields. Unknown
    fields are accepted and preserved in raw_events.raw_json. The normalization
    pipeline extracts only the typed fields it knows about; everything else is
    archived for future reprocessing without requiring a schema migration.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: str  # raw timestamp string; parsed to datetime in normalization
    source: str  # sensor identifier: 'cowrie', 'dionaea', 'custom', etc.
    type: str  # sensor-native event type; mapped to canonical event_type in normalization
    data: dict[str, Any] = Field(default_factory=dict)


class HoneypotEvent(BaseModel):
    """
    Canonical event form after normalization. Written to the events table.

    ingested_at and source are carried here so the repository can populate
    raw_events from a single object, but insert_event() writes only the
    columns present in the events table. schema_version enables selective
    reprocessing when extraction logic changes without a DB migration.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    ts: AwareDatetime
    ingested_at: AwareDatetime  # when LegionTrap received the event (UTC)
    source: str  # written to raw_events only, not to events table
    event_type: str  # canonical type from event_types lookup table
    src_ip: str | None = None
    dst_port: int | None = None
    protocol: str | None = None  # 'tcp', 'udp'
    service: str | None = None  # 'ssh', 'http', 'ftp', 'telnet'
    schema_version: int = 1


class EnrichedEvent(HoneypotEvent):
    """
    HoneypotEvent extended with GeoIP context. Produced by Phase 3 enrichment.

    GeoIP fields are nullable: enrichment failures (IP not in database, private
    IP, lookup error) must not cause ingestion failures. The event is accepted
    with NULL GeoIP fields if enrichment cannot complete.
    """

    country_code: str | None = None  # ISO 3166-1 alpha-2
    country_name: str | None = None
    city: str | None = None
    asn: int | None = None  # ASN number
    asn_org: str | None = None  # ASN organization name


class IngestError(BaseModel):
    """Per-event failure record included in IngestReceipt.errors."""

    index: int  # position of the failing event in the request batch (0-based)
    reason: str  # human-readable validation or normalization failure message


class IngestRequest(BaseModel):
    """Request body for POST /api/ingest."""

    events: list[RawEvent] = Field(..., min_length=1, max_length=500)


class IngestReceipt(BaseModel):
    """Response body for POST /api/ingest."""

    batch_id: str
    accepted: int
    rejected: int
    duplicate: int
    errors: list[IngestError] = Field(default_factory=list)
