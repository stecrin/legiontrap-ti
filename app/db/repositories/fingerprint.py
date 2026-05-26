"""Fingerprint repository methods: reads and writes for behavioral_fingerprints.

All SQL lives in this module.  No application logic, no fingerprint computation.
The caller owns the session and transaction boundary.

PostgreSQL-compatibility rules enforced here:
  - INSERT ... ON CONFLICT(source_ip) DO UPDATE SET (not INSERT OR REPLACE)
  - No json_extract() in SQL WHERE clauses
  - No dialect-specific datetime functions; timestamps are application-inserted
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase


class FingerprintRepository(RepositoryBase):
    def get_events_for_fingerprint(self, ip: str) -> list[dict[str, Any]]:
        """Return all events for ip joined with their raw_data.

        Ordered chronologically ascending.  Each row becomes one entry in the
        event list consumed by the sequence extraction utilities.

        The raw_json column stores the full serialised RawEvent.  Only the
        data sub-dict is extracted here; the rest is discarded before the
        caller sees it.  This keeps credential fields (if any) constrained
        to the raw_data key and out of other columns.
        """
        rows = self._session.execute(
            text("""
                SELECT e.ts, e.dst_port, e.event_type, e.service, r.raw_json
                FROM events e
                JOIN raw_events r ON e.id = r.id
                WHERE e.src_ip = :ip
                ORDER BY e.ts ASC
            """),
            {"ip": ip},
        ).fetchall()

        result: list[dict[str, Any]] = []
        for ts, dst_port, event_type, service, raw_json_str in rows:
            try:
                parsed = json.loads(raw_json_str)
                raw_data: dict[str, Any] = parsed.get("data") or {}
                source: str = parsed.get("source") or ""
            except (json.JSONDecodeError, AttributeError, TypeError):
                raw_data = {}
                source = ""
            result.append(
                {
                    "ts": ts,
                    "dst_port": dst_port,
                    "event_type": event_type,
                    "service": service,
                    "source": source,
                    "raw_data": raw_data,
                }
            )
        return result

    def upsert_behavioral_fingerprint(
        self,
        ip: str,
        fingerprint_version: int,
        computed_at: str,
        event_count: int,
        timing_features: str | None,
        sequence_features: str | None,
        protocol_features: str | None,
        credential_features: str | None,
        target_features: str | None,
        tool_signals: str | None,
        confidence: float,
    ) -> None:
        """Insert or update the behavioral fingerprint for ip.

        On first insertion for an ip: creates a new row with a fresh UUID.
        On subsequent calls (recomputation): updates all feature columns in
        place; the row's primary key (id) is preserved.

        Uses INSERT ... ON CONFLICT(source_ip) DO UPDATE, which is identical
        syntax in both SQLite (3.24+) and PostgreSQL.
        """
        self._session.execute(
            text("""
                INSERT INTO behavioral_fingerprints (
                    id, source_ip, fingerprint_version, computed_at,
                    event_count_at_computation, timing_features, sequence_features,
                    protocol_features, credential_features, target_features,
                    tool_signals, confidence
                ) VALUES (
                    :id, :source_ip, :fingerprint_version, :computed_at,
                    :event_count, :timing_features, :sequence_features,
                    :protocol_features, :credential_features, :target_features,
                    :tool_signals, :confidence
                )
                ON CONFLICT(source_ip) DO UPDATE SET
                    fingerprint_version        = excluded.fingerprint_version,
                    computed_at                = excluded.computed_at,
                    event_count_at_computation = excluded.event_count_at_computation,
                    timing_features            = excluded.timing_features,
                    sequence_features          = excluded.sequence_features,
                    protocol_features          = excluded.protocol_features,
                    credential_features        = excluded.credential_features,
                    target_features            = excluded.target_features,
                    tool_signals               = excluded.tool_signals,
                    confidence                 = excluded.confidence
            """),
            {
                "id": str(uuid.uuid4()),
                "source_ip": ip,
                "fingerprint_version": fingerprint_version,
                "computed_at": computed_at,
                "event_count": event_count,
                "timing_features": timing_features,
                "sequence_features": sequence_features,
                "protocol_features": protocol_features,
                "credential_features": credential_features,
                "target_features": target_features,
                "tool_signals": tool_signals,
                "confidence": confidence,
            },
        )

    def get_behavioral_fingerprint(self, ip: str) -> dict[str, Any] | None:
        """Return the stored fingerprint for ip, or None if not found.

        Used by tests and future intelligence endpoints.  Feature category
        values are returned as raw JSON strings (or None); callers parse them.
        """
        row = self._session.execute(
            text("""
                SELECT id, source_ip, fingerprint_version, computed_at,
                       event_count_at_computation, timing_features, sequence_features,
                       protocol_features, credential_features, target_features,
                       tool_signals, confidence
                FROM behavioral_fingerprints
                WHERE source_ip = :ip
            """),
            {"ip": ip},
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "source_ip": row[1],
            "fingerprint_version": row[2],
            "computed_at": row[3],
            "event_count_at_computation": row[4],
            "timing_features": row[5],
            "sequence_features": row[6],
            "protocol_features": row[7],
            "credential_features": row[8],
            "target_features": row[9],
            "tool_signals": row[10],
            "confidence": row[11],
        }
