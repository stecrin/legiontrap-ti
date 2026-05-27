"""Fingerprint history repository — append-only writes for fingerprint_history.

All SQL lives here.  No mutation methods are provided: history records are
immutable longitudinal snapshots.  There is no update_fingerprint_history()
and no delete_fingerprint_history().

Each row captures a complete fingerprint snapshot at a point in time:
  - The behavioral_fingerprints table stores only the latest fingerprint per IP.
  - This table accumulates every recomputation for longitudinal analysis.

Content rules (§11.2):
  - Feature columns store statistical summaries and distributions only.
  - No raw credentials, no raw payloads, no raw event content.
  - tool_signals is intentionally omitted — it is not a stability-relevant
    dimension and may contain tool-name strings that could encode identifiable
    information across versions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "fingerprint_id": row[1],
        "source_ip": row[2],
        "campaign_id": row[3],
        "fingerprint_version": row[4],
        "computed_at": row[5],
        "event_count_at_computation": row[6],
        "confidence": row[7],
        "timing_features": row[8],
        "sequence_features": row[9],
        "protocol_features": row[10],
        "credential_features": row[11],
        "target_features": row[12],
        "created_at": row[13],
    }


_SELECT_COLS = """
    SELECT id, fingerprint_id, source_ip, campaign_id,
           fingerprint_version, computed_at, event_count_at_computation,
           confidence, timing_features, sequence_features, protocol_features,
           credential_features, target_features, created_at
    FROM fingerprint_history
"""


class FingerprintHistoryRepository(RepositoryBase):
    def insert_fingerprint_history(
        self,
        *,
        history_id: str | None = None,
        fingerprint_id: str | None = None,
        source_ip: str,
        campaign_id: str | None = None,
        fingerprint_version: int,
        computed_at: str,
        event_count_at_computation: int,
        confidence: float,
        timing_features: str | None = None,
        sequence_features: str | None = None,
        protocol_features: str | None = None,
        credential_features: str | None = None,
        target_features: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Append a fingerprint snapshot to the history table and return it.

        This is the only write method.  No update or delete path exists.
        The returned dict reflects the inserted row.
        """
        hid = history_id or str(uuid.uuid4())
        now = created_at or datetime.now(UTC).isoformat()
        self._session.execute(
            text("""
                INSERT INTO fingerprint_history (
                    id, fingerprint_id, source_ip, campaign_id,
                    fingerprint_version, computed_at, event_count_at_computation,
                    confidence, timing_features, sequence_features,
                    protocol_features, credential_features, target_features,
                    created_at
                ) VALUES (
                    :id, :fingerprint_id, :source_ip, :campaign_id,
                    :fingerprint_version, :computed_at, :event_count_at_computation,
                    :confidence, :timing_features, :sequence_features,
                    :protocol_features, :credential_features, :target_features,
                    :created_at
                )
            """),
            {
                "id": hid,
                "fingerprint_id": fingerprint_id,
                "source_ip": source_ip,
                "campaign_id": campaign_id,
                "fingerprint_version": fingerprint_version,
                "computed_at": computed_at,
                "event_count_at_computation": event_count_at_computation,
                "confidence": confidence,
                "timing_features": timing_features,
                "sequence_features": sequence_features,
                "protocol_features": protocol_features,
                "credential_features": credential_features,
                "target_features": target_features,
                "created_at": now,
            },
        )
        return self.get_fingerprint_history_entry(hid)  # type: ignore[return-value]

    def get_fingerprint_history_entry(self, history_id: str) -> dict[str, Any] | None:
        """Return a single history record by id, or None if not found."""
        row = self._session.execute(
            text(_SELECT_COLS + "WHERE id = :id"),
            {"id": history_id},
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def list_fingerprint_history_for_ip(
        self,
        source_ip: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return history records for an IP, oldest first.

        Oldest first is the natural order for longitudinal analysis:
        each record represents a point further along the behavioral timeline.
        """
        rows = self._session.execute(
            text(_SELECT_COLS + "WHERE source_ip = :ip ORDER BY computed_at ASC LIMIT :limit"),
            {"ip": source_ip, "limit": limit},
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def list_fingerprint_history_for_campaign(
        self,
        campaign_id: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return history records for a campaign, oldest first."""
        rows = self._session.execute(
            text(_SELECT_COLS + "WHERE campaign_id = :cid ORDER BY computed_at ASC LIMIT :limit"),
            {"cid": campaign_id, "limit": limit},
        ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def count_fingerprint_history_for_ip(self, source_ip: str) -> int:
        """Return the number of history records for an IP."""
        row = self._session.execute(
            text("SELECT COUNT(*) FROM fingerprint_history WHERE source_ip = :ip"),
            {"ip": source_ip},
        ).fetchone()
        return int(row[0]) if row else 0
