"""
Write-path repository methods: inserts, upserts, updates, deletes.

All mutations belong here. Callers own the session and transaction boundary;
these methods execute SQL but never commit or rollback.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase
from app.schemas.models import EnrichedEvent, HoneypotEvent, RawEvent


class WriteRepository(RepositoryBase):
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

    def update_source_ip_intelligence(
        self,
        ip: str,
        tags: list[str],
        reputation_score: float,
    ) -> None:
        """Update tags and reputation_score on an existing source_ips row.

        tags is serialized as a sorted JSON array. No-op if ip is not in
        source_ips (should not occur in normal operation — always called
        after upsert_source_ip).
        """
        self._session.execute(
            text("""
                UPDATE source_ips
                SET tags = :tags, reputation_score = :score
                WHERE ip = :ip
                """),
            {"ip": ip, "tags": json.dumps(tags), "score": reputation_score},
        )

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
