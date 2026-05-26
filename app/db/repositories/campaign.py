"""Campaign repository methods: reads and writes for campaign tables.

All SQL lives in this module.  No clustering logic or similarity computation.
The caller owns the session and transaction boundary.

PostgreSQL-compatibility rules enforced here:
  - INSERT ... ON CONFLICT DO NOTHING (not INSERT OR IGNORE)
  - No dialect-specific datetime functions; timestamps are application-inserted
  - No json_extract() in SQL WHERE clauses
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase


class CampaignRepository(RepositoryBase):
    def create_campaign(
        self,
        campaign_id: str,
        name: str,
        status: str,
        confidence: float,
        first_seen: str,
        last_seen: str,
        member_ip_count: int,
        created_at: str,
        updated_at: str,
    ) -> None:
        """Insert a new campaign row.  campaign_id must be caller-generated."""
        self._session.execute(
            text("""
                INSERT INTO campaigns (
                    id, name, status, confidence,
                    first_seen, last_seen, dormant_since,
                    reactivation_count, member_ip_count,
                    attack_tactic_dist, top_target_ports, notes,
                    created_at, updated_at
                ) VALUES (
                    :id, :name, :status, :confidence,
                    :first_seen, :last_seen, NULL,
                    0, :member_ip_count,
                    NULL, NULL, NULL,
                    :created_at, :updated_at
                )
            """),
            {
                "id": campaign_id,
                "name": name,
                "status": status,
                "confidence": confidence,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "member_ip_count": member_ip_count,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        """Return full campaign row as dict, or None if not found."""
        row = self._session.execute(
            text("""
                SELECT id, name, status, confidence,
                       first_seen, last_seen, dormant_since,
                       reactivation_count, member_ip_count,
                       attack_tactic_dist, top_target_ports, notes,
                       created_at, updated_at
                FROM campaigns WHERE id = :id
            """),
            {"id": campaign_id},
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "status": row[2],
            "confidence": row[3],
            "first_seen": row[4],
            "last_seen": row[5],
            "dormant_since": row[6],
            "reactivation_count": row[7],
            "member_ip_count": row[8],
            "attack_tactic_dist": row[9],
            "top_target_ports": row[10],
            "notes": row[11],
            "created_at": row[12],
            "updated_at": row[13],
        }

    def get_campaigns_for_clustering(self) -> list[dict[str, Any]]:
        """Return active/dormant/reactivated campaigns with a representative fingerprint.

        The representative fingerprint is the stored fingerprint of the
        most-recently-active member IP for each campaign.

        Campaigns with no members or whose most-recent member has no
        stored fingerprint are silently excluded (no candidate to compare
        against).
        """
        campaign_rows = self._session.execute(text("""
                SELECT id, status, last_seen
                FROM campaigns
                WHERE status IN ('active', 'dormant', 'reactivated')
            """)).fetchall()

        if not campaign_rows:
            return []

        results: list[dict[str, Any]] = []
        for cid, status, last_seen in campaign_rows:
            member_row = self._session.execute(
                text("""
                    SELECT source_ip FROM campaign_members
                    WHERE campaign_id = :cid
                    ORDER BY last_active DESC LIMIT 1
                """),
                {"cid": cid},
            ).fetchone()
            if member_row is None:
                continue

            fp_row = self._session.execute(
                text("""
                    SELECT timing_features, sequence_features, protocol_features,
                           credential_features, target_features, confidence
                    FROM behavioral_fingerprints
                    WHERE source_ip = :ip
                """),
                {"ip": member_row[0]},
            ).fetchone()
            if fp_row is None:
                continue

            results.append(
                {
                    "campaign_id": cid,
                    "status": status,
                    "last_seen": last_seen,
                    "timing_features": fp_row[0],
                    "sequence_features": fp_row[1],
                    "protocol_features": fp_row[2],
                    "credential_features": fp_row[3],
                    "target_features": fp_row[4],
                    "confidence": fp_row[5],
                }
            )

        return results

    def get_campaign_member_by_ip(self, source_ip: str) -> dict[str, Any] | None:
        """Return the campaign_members row for source_ip, or None if unassigned."""
        row = self._session.execute(
            text("""
                SELECT campaign_id, source_ip, confidence, added_at, last_active
                FROM campaign_members
                WHERE source_ip = :ip
            """),
            {"ip": source_ip},
        ).fetchone()
        if row is None:
            return None
        return {
            "campaign_id": row[0],
            "source_ip": row[1],
            "confidence": row[2],
            "added_at": row[3],
            "last_active": row[4],
        }

    def add_campaign_member(
        self,
        campaign_id: str,
        source_ip: str,
        confidence: float,
        added_at: str,
        last_active: str,
    ) -> None:
        """Insert a new campaign_members row."""
        self._session.execute(
            text("""
                INSERT INTO campaign_members
                    (campaign_id, source_ip, confidence, added_at, last_active)
                VALUES (:campaign_id, :source_ip, :confidence, :added_at, :last_active)
            """),
            {
                "campaign_id": campaign_id,
                "source_ip": source_ip,
                "confidence": confidence,
                "added_at": added_at,
                "last_active": last_active,
            },
        )

    def update_campaign_member_last_active(
        self,
        campaign_id: str,
        source_ip: str,
        last_active: str,
    ) -> None:
        """Update the last_active timestamp for an existing campaign member."""
        self._session.execute(
            text("""
                UPDATE campaign_members
                SET last_active = :last_active
                WHERE campaign_id = :campaign_id AND source_ip = :source_ip
            """),
            {
                "campaign_id": campaign_id,
                "source_ip": source_ip,
                "last_active": last_active,
            },
        )

    def insert_campaign_observation(
        self,
        campaign_id: str,
        source_ip: str,
        observed_at: str,
        event_count: int,
        is_reactivation: bool,
        dormancy_gap_days: float | None,
        notes: str | None,
    ) -> None:
        """Insert a new campaign_observations row."""
        self._session.execute(
            text("""
                INSERT INTO campaign_observations
                    (id, campaign_id, source_ip, observed_at, event_count,
                     is_reactivation, dormancy_gap_days, notes)
                VALUES
                    (:id, :campaign_id, :source_ip, :observed_at, :event_count,
                     :is_reactivation, :dormancy_gap_days, :notes)
            """),
            {
                "id": str(uuid.uuid4()),
                "campaign_id": campaign_id,
                "source_ip": source_ip,
                "observed_at": observed_at,
                "event_count": event_count,
                "is_reactivation": 1 if is_reactivation else 0,
                "dormancy_gap_days": dormancy_gap_days,
                "notes": notes,
            },
        )

    def update_campaign_on_association(
        self,
        campaign_id: str,
        last_seen: str,
        updated_at: str,
        new_member_ip_count_delta: int,
        is_reactivation: bool,
    ) -> None:
        """Update campaign metadata after a new IP is associated.

        When is_reactivation is True:
          - status → 'reactivated'
          - dormant_since → NULL
          - reactivation_count += 1

        new_member_ip_count_delta is 1 for a new member, 0 for an existing
        member whose activity is being recorded.
        """
        if is_reactivation:
            self._session.execute(
                text("""
                    UPDATE campaigns
                    SET last_seen = :last_seen,
                        updated_at = :updated_at,
                        member_ip_count = member_ip_count + :delta,
                        status = 'reactivated',
                        dormant_since = NULL,
                        reactivation_count = reactivation_count + 1
                    WHERE id = :campaign_id
                """),
                {
                    "campaign_id": campaign_id,
                    "last_seen": last_seen,
                    "updated_at": updated_at,
                    "delta": new_member_ip_count_delta,
                },
            )
        else:
            self._session.execute(
                text("""
                    UPDATE campaigns
                    SET last_seen = :last_seen,
                        updated_at = :updated_at,
                        member_ip_count = member_ip_count + :delta
                    WHERE id = :campaign_id
                """),
                {
                    "campaign_id": campaign_id,
                    "last_seen": last_seen,
                    "updated_at": updated_at,
                    "delta": new_member_ip_count_delta,
                },
            )

    def get_campaign_observations(self, campaign_id: str) -> list[dict[str, Any]]:
        """Return all observations for a campaign, ordered by observed_at."""
        rows = self._session.execute(
            text("""
                SELECT id, campaign_id, source_ip, observed_at, event_count,
                       is_reactivation, dormancy_gap_days, notes
                FROM campaign_observations
                WHERE campaign_id = :campaign_id
                ORDER BY observed_at ASC
            """),
            {"campaign_id": campaign_id},
        ).fetchall()
        return [
            {
                "id": r[0],
                "campaign_id": r[1],
                "source_ip": r[2],
                "observed_at": r[3],
                "event_count": r[4],
                "is_reactivation": bool(r[5]),
                "dormancy_gap_days": r[6],
                "notes": r[7],
            }
            for r in rows
        ]
