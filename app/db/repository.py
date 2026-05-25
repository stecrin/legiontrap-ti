"""
EventRepository — the single SQL boundary for LegionTrap TI.

All SQL lives here. Routers call repository methods; they never write SQL.
The caller owns the session and therefore the transaction boundary.

Construction pattern (caller controls atomicity):
    with get_session() as session:
        repo = EventRepository(session)
        repo.insert_raw_event(raw)
        repo.insert_event(event)
        repo.upsert_source_ip(event.src_ip, event.ts)
    # session commits on clean exit, rolls back on exception

No FastAPI, router, or application imports belong in this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.models import EnrichedEvent, HoneypotEvent, RawEvent


class EventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        # Lazy-loaded cache of valid event_type IDs from the event_types table.
        # Populated on first insert_event() call; valid for the repository lifetime.
        self._valid_event_types: frozenset[str] | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_valid_event_types(self) -> frozenset[str]:
        """
        Load event_type IDs from the event_types lookup table.
        Called once per repository instance; result is cached.
        Keeps the coercion logic in sync with the actual DB state rather
        than a hardcoded list.
        """
        if self._valid_event_types is None:
            rows = self._session.execute(text("SELECT id FROM event_types")).fetchall()
            self._valid_event_types = frozenset(row[0] for row in rows)
        return self._valid_event_types

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def insert_raw_event(self, raw: RawEvent) -> None:
        """
        Insert into raw_events. Raises sqlalchemy.exc.IntegrityError on duplicate
        id — the caller treats this as a deduplication signal (do not retry).

        raw_json stores the full serialised RawEvent including extra sensor fields
        not extracted during normalisation. This is the immutable provenance record.
        """
        self._session.execute(
            text("""
                INSERT INTO raw_events (id, ts, ingested_at, source, raw_json)
                VALUES (:id, :ts, :ingested_at, :source, :raw_json)
                """),
            {
                "id": raw.id,
                "ts": raw.ts,
                "ingested_at": datetime.now(UTC).isoformat(),
                "source": raw.source,
                "raw_json": raw.model_dump_json(),
            },
        )

    def insert_event(self, event: HoneypotEvent | EnrichedEvent) -> None:
        """
        Insert into the events table.

        Explicitly excludes `ingested_at` and `source` — both fields exist on
        HoneypotEvent to allow raw_events population from the same object, but
        neither is a column in the events table. Passing them to the INSERT would
        raise a column-not-found error; the explicit mapping below is the guard.

        `event_type` is coerced to "unknown" if the value is not in the
        event_types lookup table. This prevents FK violations for sensor-specific
        types that have not yet been mapped. Callers should use
        normalize_event_type() before calling this method.

        `campaign_id` is always NULL in Phase 1 — the campaigns table does not
        exist until Phase 6.
        """
        valid = self._load_valid_event_types()
        event_type = event.event_type if event.event_type in valid else "unknown"

        # GeoIP fields exist only on EnrichedEvent; default to NULL for HoneypotEvent.
        country_code = country_name = city = None
        asn: int | None = None
        asn_org: str | None = None
        if isinstance(event, EnrichedEvent):
            country_code = event.country_code
            country_name = event.country_name
            city = event.city
            asn = event.asn
            asn_org = event.asn_org

        self._session.execute(
            text("""
                INSERT INTO events (
                    id, ts, src_ip, dst_port, protocol, event_type,
                    service, country_code, country_name, city, asn, asn_org,
                    campaign_id, schema_version
                ) VALUES (
                    :id, :ts, :src_ip, :dst_port, :protocol, :event_type,
                    :service, :country_code, :country_name, :city, :asn, :asn_org,
                    :campaign_id, :schema_version
                )
                """),
            {
                "id": event.id,
                "ts": event.ts.isoformat(),
                "src_ip": event.src_ip,
                "dst_port": event.dst_port,
                "protocol": event.protocol,
                "event_type": event_type,
                "service": event.service,
                "country_code": country_code,
                "country_name": country_name,
                "city": city,
                "asn": asn,
                "asn_org": asn_org,
                "campaign_id": None,
                "schema_version": event.schema_version,
            },
        )

    def upsert_source_ip(
        self,
        ip: str,
        ts: datetime,
        country_code: str | None = None,
        country_name: str | None = None,
        asn: int | None = None,
        asn_org: str | None = None,
    ) -> None:
        """
        Upsert into source_ips per the documented pattern in DATABASE_SCHEMA.md.

        On first occurrence: inserts with event_count=1 and first_seen=ts.
        On subsequent occurrences: increments event_count, updates last_seen.
        first_seen is preserved on conflict.

        Uses standard INSERT ... ON CONFLICT DO UPDATE syntax, which is supported
        identically by SQLite (3.24+) and PostgreSQL. No dialect-specific imports.
        """
        self._session.execute(
            text("""
                INSERT INTO source_ips (
                    ip, first_seen, last_seen, event_count,
                    country_code, country_name, asn, asn_org
                )
                VALUES (:ip, :ts, :ts, 1, :country_code, :country_name, :asn, :asn_org)
                ON CONFLICT(ip) DO UPDATE SET
                    last_seen   = excluded.last_seen,
                    event_count = event_count + 1
                """),
            {
                "ip": ip,
                "ts": ts.isoformat(),
                "country_code": country_code,
                "country_name": country_name,
                "asn": asn,
                "asn_org": asn_org,
            },
        )

    # ------------------------------------------------------------------
    # Existence check — deduplication gate
    # ------------------------------------------------------------------

    def event_exists(self, event_id: str) -> bool:
        """
        Return True if event_id is already present in raw_events.

        Used by the ingestion pipeline to detect duplicate sensor submissions
        (sensor retries, JSONL re-imports). Positive result → skip the event
        and increment the 'duplicate' counter in IngestReceipt.
        """
        row = self._session.execute(
            text("SELECT 1 FROM raw_events WHERE id = :id LIMIT 1"),
            {"id": event_id},
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Read methods — used by routers after Phase 1B migration to SQLite
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """
        Return aggregate event counts for GET /api/stats.

        last_24h uses ISO8601 string comparison with SQLite's datetime()
        function. Valid because all ts values are stored as UTC isoformat
        strings, which sort lexicographically in chronological order.
        """
        row = self._session.execute(text("""
                SELECT
                    COUNT(*)                 AS total_events,
                    COUNT(DISTINCT src_ip)   AS unique_ips,
                    SUM(
                        CASE WHEN datetime(ts) >= datetime('now', '-24 hours')
                        THEN 1 ELSE 0 END
                    )                        AS last_24h
                FROM events
                """)).fetchone()
        if row is None:
            return {"total_events": 0, "unique_ips": 0, "last_24h": 0}
        return {
            "total_events": row[0] or 0,
            "unique_ips": row[1] or 0,
            "last_24h": row[2] or 0,
        }

    def list_events(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        Return events newest-first for GET /api/events.
        Column set matches the events table schema exactly.
        """
        rows = self._session.execute(
            text("""
                SELECT id, ts, src_ip, dst_port, protocol, event_type,
                       service, country_code, country_name, city, asn, asn_org,
                       campaign_id, schema_version
                FROM events
                ORDER BY ts DESC
                LIMIT :limit OFFSET :offset
                """),
            {"limit": limit, "offset": offset},
        ).fetchall()
        keys = [
            "id",
            "ts",
            "src_ip",
            "dst_port",
            "protocol",
            "event_type",
            "service",
            "country_code",
            "country_name",
            "city",
            "asn",
            "asn_org",
            "campaign_id",
            "schema_version",
        ]
        return [dict(zip(keys, row, strict=False)) for row in rows]

    def get_unique_public_ips(self) -> list[str]:
        """
        Return sorted unique source IPs for IOC export endpoints.
        NULL src_ip rows are excluded — events without an extractable IP
        are accepted during ingest but must not appear in IOC feeds.
        """
        rows = self._session.execute(text("""
                SELECT DISTINCT src_ip
                FROM events
                WHERE src_ip IS NOT NULL
                ORDER BY src_ip
                """)).fetchall()
        return [row[0] for row in rows]

    def insert_audit_log(
        self,
        event_type: str,
        source_ip: str | None = None,
        detail: str | None = None,
    ) -> None:
        """
        Insert a row into audit_log. Called best-effort after successful ingest batch.
        The caller is responsible for committing the session.
        """
        self._session.execute(
            text("""
                INSERT INTO audit_log (id, ts, event_type, source_ip, detail)
                VALUES (:id, :ts, :event_type, :source_ip, :detail)
                """),
            {
                "id": str(uuid.uuid4()),
                "ts": datetime.now(UTC).isoformat(),
                "event_type": event_type,
                "source_ip": source_ip,
                "detail": detail,
            },
        )

    def delete_events_before(self, cutoff: datetime) -> int:
        """
        Delete events and orphaned raw_events older than cutoff.

        Deletes from events (FK child) first, then removes raw_events rows that
        no longer have a matching events row. Returns the count of events rows
        deleted.
        """
        result = self._session.execute(
            text("DELETE FROM events WHERE ts < :cutoff"),
            {"cutoff": cutoff.isoformat()},
        )
        deleted = result.rowcount
        self._session.execute(
            text(
                "DELETE FROM raw_events " "WHERE ts < :cutoff AND id NOT IN (SELECT id FROM events)"
            ),
            {"cutoff": cutoff.isoformat()},
        )
        return deleted
