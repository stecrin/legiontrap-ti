"""Alert repository — Phase 7 Group A.

Read/write methods for behavioral_alerts.

Invariants:
  - Alerts are informational only.  No method here mutates campaigns,
    fingerprints, clustering decisions, or weight profiles.
  - Deduplication is enforced by has_open_alert(): callers must check before
    inserting.  The job layer owns the deduplication logic.
  - acknowledged_at IS NOT NULL means the alert has been reviewed by an
    operator.  Acknowledged alerts do not block new alerts.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase

_ALERT_SELECT = """
    SELECT id, campaign_id, alert_type, dimension,
           threshold_configured, observed_value, stability_snapshot_json,
           triggered_at, acknowledged_at, acknowledged_notes
    FROM behavioral_alerts
"""


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "campaign_id": row[1],
        "alert_type": row[2],
        "dimension": row[3],
        "threshold_configured": row[4],
        "observed_value": row[5],
        "stability_snapshot": json.loads(row[6]) if row[6] else {},
        "triggered_at": row[7],
        "acknowledged_at": row[8],
        "acknowledged_notes": row[9],
        "acknowledged": row[8] is not None,
    }


class AlertRepository(RepositoryBase):
    def has_open_alert(self, campaign_id: str, dimension: str | None) -> bool:
        """Return True if an unacknowledged alert exists for (campaign_id, dimension).

        dimension is None for composite alerts, a dimension name for per-dimension
        alerts.  This is the deduplication gate used by the alert generation job.
        """
        if dimension is None:
            row = self._session.execute(
                text("""
                    SELECT 1 FROM behavioral_alerts
                    WHERE campaign_id = :cid
                      AND dimension IS NULL
                      AND acknowledged_at IS NULL
                    LIMIT 1
                """),
                {"cid": campaign_id},
            ).fetchone()
        else:
            row = self._session.execute(
                text("""
                    SELECT 1 FROM behavioral_alerts
                    WHERE campaign_id = :cid
                      AND dimension = :dim
                      AND acknowledged_at IS NULL
                    LIMIT 1
                """),
                {"cid": campaign_id, "dim": dimension},
            ).fetchone()
        return row is not None

    def insert_alert(
        self,
        campaign_id: str,
        alert_type: str,
        dimension: str | None,
        threshold_configured: float,
        observed_value: float,
        stability_snapshot: dict[str, Any],
        triggered_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new behavioral alert row and return it."""
        aid = str(uuid.uuid4())
        now = triggered_at or datetime.now(UTC).isoformat()
        self._session.execute(
            text("""
                INSERT INTO behavioral_alerts (
                    id, campaign_id, alert_type, dimension,
                    threshold_configured, observed_value,
                    stability_snapshot_json, triggered_at
                ) VALUES (
                    :id, :campaign_id, :alert_type, :dimension,
                    :threshold_configured, :observed_value,
                    :stability_snapshot_json, :triggered_at
                )
            """),
            {
                "id": aid,
                "campaign_id": campaign_id,
                "alert_type": alert_type,
                "dimension": dimension,
                "threshold_configured": threshold_configured,
                "observed_value": observed_value,
                "stability_snapshot_json": json.dumps(stability_snapshot),
                "triggered_at": now,
            },
        )
        row = self._session.execute(
            text(_ALERT_SELECT + "WHERE id = :id"),
            {"id": aid},
        ).fetchone()
        return _row_to_dict(row)  # type: ignore[arg-type]

    def acknowledge_alert(
        self,
        alert_id: str,
        notes: str | None = None,
        acknowledged_at: str | None = None,
    ) -> dict[str, Any] | None:
        """Mark an alert acknowledged.  Returns the updated row, or None if not found."""
        now = acknowledged_at or datetime.now(UTC).isoformat()
        self._session.execute(
            text("""
                UPDATE behavioral_alerts
                SET acknowledged_at = :ack_at, acknowledged_notes = :notes
                WHERE id = :id
            """),
            {"ack_at": now, "notes": notes, "id": alert_id},
        )
        row = self._session.execute(
            text(_ALERT_SELECT + "WHERE id = :id"),
            {"id": alert_id},
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        """Return a single alert row, or None."""
        row = self._session.execute(
            text(_ALERT_SELECT + "WHERE id = :id"),
            {"id": alert_id},
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def list_alerts(
        self,
        *,
        campaign_id: str | None = None,
        include_acknowledged: bool = False,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return alerts ordered by triggered_at DESC.

        By default, only unacknowledged alerts are returned.
        """
        params: dict[str, Any] = {"limit": limit}
        clauses: list[str] = []
        if campaign_id is not None:
            clauses.append("campaign_id = :campaign_id")
            params["campaign_id"] = campaign_id
        if not include_acknowledged:
            clauses.append("acknowledged_at IS NULL")
        where = ("WHERE " + " AND ".join(clauses) + " ") if clauses else ""
        rows = self._session.execute(
            text(_ALERT_SELECT + where + "ORDER BY triggered_at DESC LIMIT :limit"),
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
