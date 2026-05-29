"""Weight profile repository — Phase 7 Group A.

Read/write methods for campaign_weight_profiles.

Invariants:
  - No row is created automatically.  The weight profile job creates rows only
    after WEIGHT_PROFILE_MIN_REVIEWS reviews have been processed.
  - adjustment_log_json is append-only: existing entries are never removed or
    modified.  The job is idempotent: observation IDs already present in the
    log are silently skipped.
  - No method here modifies campaign membership, clustering decisions, or any
    table outside campaign_weight_profiles.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase

_DIMS = ("timing", "sequence", "protocol", "credential", "target")

_PROFILE_SELECT = """
    SELECT campaign_id, weight_timing, weight_sequence, weight_protocol,
           weight_credential, weight_target, review_count, confirmed_count,
           denied_count, adjustment_log_json, computed_at, updated_at
    FROM campaign_weight_profiles
"""


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "campaign_id": row[0],
        "weights": {
            "timing": row[1],
            "sequence": row[2],
            "protocol": row[3],
            "credential": row[4],
            "target": row[5],
        },
        "review_count": row[6],
        "confirmed_count": row[7],
        "denied_count": row[8],
        "adjustment_log": json.loads(row[9]) if row[9] else [],
        "computed_at": row[10],
        "updated_at": row[11],
    }


class WeightProfileRepository(RepositoryBase):
    def get_weight_profile(self, campaign_id: str) -> dict[str, Any] | None:
        """Return the weight profile for campaign_id, or None if not present."""
        row = self._session.execute(
            text(_PROFILE_SELECT + "WHERE campaign_id = :cid"),
            {"cid": campaign_id},
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    def get_weight_profile_weights_only(self, campaign_id: str) -> dict[str, float] | None:
        """Return only the weights dict for campaign_id, or None if not present.

        Used by the clustering algorithm integration point.  Avoids deserializing
        the full adjustment log for every candidate campaign.
        """
        row = self._session.execute(
            text("""
                SELECT weight_timing, weight_sequence, weight_protocol,
                       weight_credential, weight_target
                FROM campaign_weight_profiles
                WHERE campaign_id = :cid
            """),
            {"cid": campaign_id},
        ).fetchone()
        if row is None:
            return None
        return {
            "timing": row[0],
            "sequence": row[1],
            "protocol": row[2],
            "credential": row[3],
            "target": row[4],
        }

    def upsert_weight_profile(
        self,
        campaign_id: str,
        weights: dict[str, float],
        review_count: int,
        confirmed_count: int,
        denied_count: int,
        adjustment_log: list[dict[str, Any]],
        computed_at: str,
        updated_at: str,
    ) -> None:
        """Insert or replace the weight profile row for campaign_id."""
        self._session.execute(
            text("""
                INSERT INTO campaign_weight_profiles (
                    campaign_id,
                    weight_timing, weight_sequence, weight_protocol,
                    weight_credential, weight_target,
                    review_count, confirmed_count, denied_count,
                    adjustment_log_json, computed_at, updated_at
                ) VALUES (
                    :campaign_id,
                    :weight_timing, :weight_sequence, :weight_protocol,
                    :weight_credential, :weight_target,
                    :review_count, :confirmed_count, :denied_count,
                    :adjustment_log_json, :computed_at, :updated_at
                )
                ON CONFLICT(campaign_id) DO UPDATE SET
                    weight_timing      = excluded.weight_timing,
                    weight_sequence    = excluded.weight_sequence,
                    weight_protocol    = excluded.weight_protocol,
                    weight_credential  = excluded.weight_credential,
                    weight_target      = excluded.weight_target,
                    review_count       = excluded.review_count,
                    confirmed_count    = excluded.confirmed_count,
                    denied_count       = excluded.denied_count,
                    adjustment_log_json = excluded.adjustment_log_json,
                    computed_at        = excluded.computed_at,
                    updated_at         = excluded.updated_at
            """),
            {
                "campaign_id": campaign_id,
                "weight_timing": weights["timing"],
                "weight_sequence": weights["sequence"],
                "weight_protocol": weights["protocol"],
                "weight_credential": weights["credential"],
                "weight_target": weights["target"],
                "review_count": review_count,
                "confirmed_count": confirmed_count,
                "denied_count": denied_count,
                "adjustment_log_json": json.dumps(adjustment_log),
                "computed_at": computed_at,
                "updated_at": updated_at,
            },
        )

    def list_weight_profiles(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return all weight profiles, newest computed_at first."""
        rows = self._session.execute(
            text(_PROFILE_SELECT + "ORDER BY computed_at DESC LIMIT :limit"),
            {"limit": limit},
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
