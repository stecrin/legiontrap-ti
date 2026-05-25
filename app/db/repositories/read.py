"""
Read-path repository methods: queries used by main endpoints and the ingest pipeline.

Includes core dashboard queries, the deduplication gate, and the ingest-side
intelligence cache reads (geo lookup, scoring inputs). These are kept separate
from intelligence.py because they serve different callers: ingest pipeline and
existing dashboard endpoints vs. the dedicated intelligence API.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase


class ReadRepository(RepositoryBase):
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

    def get_source_ip_geo(self, ip: str) -> dict | None:
        """
        Return cached geo fields for ip if source_ips row exists and
        country_code is populated. Returns None on cache miss (unknown IP
        or NULL country_code). Keys: country_code, country_name, asn, asn_org.
        Used by Stage 3.5 of ingest to skip the GeoIP file read for known IPs.
        """
        row = self._session.execute(
            text("""
                SELECT country_code, country_name, asn, asn_org
                FROM source_ips
                WHERE ip = :ip AND country_code IS NOT NULL
                """),
            {"ip": ip},
        ).fetchone()
        if row is None:
            return None
        return {
            "country_code": row[0],
            "country_name": row[1],
            "asn": row[2],
            "asn_org": row[3],
        }

    def get_source_ip_event_types(self, ip: str) -> list[str]:
        """Return distinct normalized event_type values seen from ip."""
        rows = self._session.execute(
            text("SELECT DISTINCT event_type FROM events WHERE src_ip = :ip"),
            {"ip": ip},
        ).fetchall()
        return [row[0] for row in rows]

    def get_source_ip_intelligence(self, ip: str) -> dict | None:
        """
        Return {tags: list[str], event_count: int} for ip from source_ips.
        Used as scoring input after upsert_source_ip. Returns None if ip not found.
        Malformed tags JSON is treated as an empty list.
        """
        row = self._session.execute(
            text("SELECT event_count, tags FROM source_ips WHERE ip = :ip"),
            {"ip": ip},
        ).fetchone()
        if row is None:
            return None
        event_count, tags_json = row
        try:
            tags: list[str] = json.loads(tags_json) if tags_json else []
        except (ValueError, TypeError):
            tags = []
        return {"event_count": event_count, "tags": tags}
