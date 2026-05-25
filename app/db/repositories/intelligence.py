"""
Intelligence query repository methods: enriched IP profiles and aggregations.

These methods serve the /api/intelligence/* endpoints exclusively. They read
from source_ips and events but never modify data. Kept separate from read.py
because they represent a distinct API surface with its own response contracts.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase


class IntelligenceRepository(RepositoryBase):
    @staticmethod
    def _source_ip_to_dict(row: Any) -> dict[str, Any]:
        """Convert a source_ips SELECT row to the base intelligence response dict.

        city is always None — source_ips does not store city; it exists only
        in the events table. The field is present in the response for forward
        compatibility with a future schema update.
        """
        (
            ip,
            first_seen,
            last_seen,
            event_count,
            country_code,
            country_name,
            asn,
            asn_org,
            reputation_score,
            tags_json,
        ) = row
        try:
            tags: list[str] = json.loads(tags_json) if tags_json else []
        except (ValueError, TypeError):
            tags = []
        return {
            "ip": ip,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "event_count": event_count,
            "country_code": country_code,
            "country_name": country_name,
            "city": None,
            "asn": asn,
            "asn_org": asn_org,
            "reputation_score": reputation_score,
            "tags": tags,
        }

    def get_source_ip_event_type_breakdown(self, ip: str) -> dict[str, int]:
        """
        Return a mapping of event_type → count for all events from ip.
        Used to populate the event_type_breakdown field in the single-IP
        intelligence profile. Returns an empty dict if ip has no events.
        """
        rows = self._session.execute(
            text("""
                SELECT event_type, COUNT(*) AS cnt
                FROM events
                WHERE src_ip = :ip
                GROUP BY event_type
                ORDER BY cnt DESC
                """),
            {"ip": ip},
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def list_source_ips(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Return source IP intelligence records sorted by reputation_score DESC,
        then event_count DESC. NULLs sort last (SQLite NULL < any non-NULL).
        Used by GET /api/intelligence/ips.
        """
        rows = self._session.execute(
            text("""
                SELECT ip, first_seen, last_seen, event_count,
                       country_code, country_name, asn, asn_org,
                       reputation_score, tags
                FROM source_ips
                ORDER BY reputation_score DESC, event_count DESC
                LIMIT :limit
                """),
            {"limit": limit},
        ).fetchall()
        return [self._source_ip_to_dict(row) for row in rows]

    def get_source_ip(self, ip: str) -> dict[str, Any] | None:
        """
        Return the full intelligence profile for a single IP, or None if unknown.

        Includes event_type_breakdown (event_type → count from the events table)
        in addition to the base source_ips fields. Used by
        GET /api/intelligence/ips/{ip}.
        """
        row = self._session.execute(
            text("""
                SELECT ip, first_seen, last_seen, event_count,
                       country_code, country_name, asn, asn_org,
                       reputation_score, tags
                FROM source_ips
                WHERE ip = :ip
                """),
            {"ip": ip},
        ).fetchone()
        if row is None:
            return None
        profile = self._source_ip_to_dict(row)
        profile["event_type_breakdown"] = self.get_source_ip_event_type_breakdown(ip)
        return profile

    def get_top_countries(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Return top countries by total event_count, aggregated across source_ips.
        Rows with NULL country_code are excluded. Sorted by event_count DESC,
        country_code ASC for deterministic output on ties.
        Used by GET /api/intelligence/top-countries.
        """
        rows = self._session.execute(
            text("""
                SELECT country_code, country_name,
                       SUM(event_count) AS event_count,
                       COUNT(ip)        AS unique_ips,
                       MIN(first_seen)  AS first_seen,
                       MAX(last_seen)   AS last_seen
                FROM source_ips
                WHERE country_code IS NOT NULL
                GROUP BY country_code, country_name
                ORDER BY event_count DESC, country_code ASC
                LIMIT :limit
                """),
            {"limit": limit},
        ).fetchall()
        return [
            {
                "country_code": row[0],
                "country_name": row[1],
                "event_count": row[2],
                "unique_ips": row[3],
                "first_seen": row[4],
                "last_seen": row[5],
            }
            for row in rows
        ]

    def get_top_asns(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Return top ASNs by total event_count, aggregated across source_ips.
        Rows with NULL asn are excluded. Sorted by event_count DESC, asn ASC
        for deterministic output on ties.
        Used by GET /api/intelligence/top-asns.
        """
        rows = self._session.execute(
            text("""
                SELECT asn, asn_org,
                       SUM(event_count) AS event_count,
                       COUNT(ip)        AS unique_ips,
                       MIN(first_seen)  AS first_seen,
                       MAX(last_seen)   AS last_seen
                FROM source_ips
                WHERE asn IS NOT NULL
                GROUP BY asn, asn_org
                ORDER BY event_count DESC, asn ASC
                LIMIT :limit
                """),
            {"limit": limit},
        ).fetchall()
        return [
            {
                "asn": row[0],
                "asn_org": row[1],
                "event_count": row[2],
                "unique_ips": row[3],
                "first_seen": row[4],
                "last_seen": row[5],
            }
            for row in rows
        ]

    def get_attack_technique_counts(self) -> list[dict[str, Any]]:
        """
        Return aggregated event counts per ATT&CK technique, joining events
        against the event_types lookup table.

        Only techniques with a non-NULL attack_technique are included.
        Sorted by event_count DESC for deterministic output.
        Used by GET /api/exports/attack-navigator.
        """
        rows = self._session.execute(text("""
                SELECT et.attack_tactic,
                       et.attack_technique,
                       et.label,
                       COUNT(e.id) AS event_count
                FROM events e
                JOIN event_types et ON e.event_type = et.id
                WHERE et.attack_technique IS NOT NULL
                GROUP BY et.attack_technique, et.attack_tactic, et.label
                ORDER BY event_count DESC
                """)).fetchall()
        return [
            {
                "attack_tactic": row[0],
                "attack_technique": row[1],
                "label": row[2],
                "event_count": row[3],
            }
            for row in rows
        ]

    def get_stix_indicator_ips(
        self, limit: int = 100, min_event_count: int = 1
    ) -> list[dict[str, Any]]:
        """
        Return source IP records eligible for STIX Indicator export.

        Filtered by minimum event count. Sorted by reputation_score DESC
        (NULLs last), then event_count DESC.
        Used by GET /api/exports/stix.
        """
        rows = self._session.execute(
            text("""
                SELECT ip, first_seen, last_seen, event_count,
                       reputation_score, tags
                FROM source_ips
                WHERE event_count >= :min_event_count
                ORDER BY reputation_score DESC, event_count DESC
                LIMIT :limit
                """),
            {"min_event_count": min_event_count, "limit": limit},
        ).fetchall()
        result = []
        for row in rows:
            ip, first_seen, last_seen, event_count, reputation_score, tags_json = row
            try:
                tags: list[str] = json.loads(tags_json) if tags_json else []
            except (ValueError, TypeError):
                tags = []
            result.append(
                {
                    "ip": ip,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "event_count": event_count,
                    "reputation_score": reputation_score,
                    "tags": tags,
                }
            )
        return result
