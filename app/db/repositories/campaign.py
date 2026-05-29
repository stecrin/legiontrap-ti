"""Campaign repository methods: reads and writes for campaign tables.

All SQL lives in this module.  No clustering logic or similarity computation.
The caller owns the session and transaction boundary.

PostgreSQL-compatibility rules enforced here:
  - INSERT ... ON CONFLICT DO NOTHING (not INSERT OR IGNORE)
  - No dialect-specific datetime functions; timestamps are application-inserted
  - No json_extract() in SQL WHERE clauses
"""

from __future__ import annotations

import json
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
                       created_at, updated_at, behavioral_stability_json
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
            "behavioral_stability_json": row[14],
        }

    def get_campaigns_for_clustering(self) -> list[dict[str, Any]]:
        """Return active/dormant/reactivated campaigns with a representative fingerprint.

        Fast path: when representative_fingerprint_json is populated on the
        campaign row, parse it directly — one SQL query for all campaigns.

        Slow path (fallback): for campaigns whose representative_fingerprint_json
        is NULL (or fails to parse), fall back to per-member + behavioral_fingerprints
        lookup.  This handles pre-migration rows and any cache-miss edge cases.

        Campaigns with no members or no stored fingerprint are silently excluded.
        """
        campaign_rows = self._session.execute(text("""
                SELECT id, status, last_seen, representative_fingerprint_json
                FROM campaigns
                WHERE status IN ('active', 'dormant', 'reactivated')
            """)).fetchall()

        if not campaign_rows:
            return []

        results: list[dict[str, Any]] = []
        for cid, status, last_seen, rep_fp_json in campaign_rows:
            if rep_fp_json is not None:
                try:
                    fp_data = json.loads(rep_fp_json)
                    results.append(
                        {
                            "campaign_id": cid,
                            "status": status,
                            "last_seen": last_seen,
                            "timing_features": fp_data.get("timing_features"),
                            "sequence_features": fp_data.get("sequence_features"),
                            "protocol_features": fp_data.get("protocol_features"),
                            "credential_features": fp_data.get("credential_features"),
                            "target_features": fp_data.get("target_features"),
                            "confidence": fp_data.get("confidence"),
                        }
                    )
                    continue
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass

            # Slow path: per-member lookup.
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

        if not results:
            return results

        # Batch-fetch weight profiles for all candidate campaigns and attach them.
        # weight_profile is None when no calibrated profile exists (uses global defaults).
        cids = [r["campaign_id"] for r in results]
        placeholders = ", ".join(f":p{i}" for i in range(len(cids)))
        params = {f"p{i}": cid for i, cid in enumerate(cids)}
        wp_rows = self._session.execute(
            text(f"""
                SELECT campaign_id,
                       weight_timing, weight_sequence, weight_protocol,
                       weight_credential, weight_target
                FROM campaign_weight_profiles
                WHERE campaign_id IN ({placeholders})
            """),
            params,
        ).fetchall()
        weight_map: dict[str, dict[str, float]] = {
            row[0]: {
                "timing": row[1],
                "sequence": row[2],
                "protocol": row[3],
                "credential": row[4],
                "target": row[5],
            }
            for row in wp_rows
        }
        for r in results:
            r["weight_profile"] = weight_map.get(r["campaign_id"])

        return results

    def update_representative_fingerprint(
        self,
        campaign_id: str,
        representative_fingerprint_json: str,
    ) -> None:
        """Cache the representative fingerprint JSON on the campaign row.

        Called after a successful fingerprint computation + clustering assignment.
        behavioral_fingerprints remains the authoritative source; this is a
        denormalized cache to avoid O(n) per-campaign member + fingerprint lookups
        in get_campaigns_for_clustering().
        """
        self._session.execute(
            text("""
                UPDATE campaigns
                SET representative_fingerprint_json = :fp_json
                WHERE id = :campaign_id
            """),
            {
                "campaign_id": campaign_id,
                "fp_json": representative_fingerprint_json,
            },
        )

    def get_representative_fingerprint(self, campaign_id: str) -> str | None:
        """Return the cached representative_fingerprint_json, or None if not set."""
        row = self._session.execute(
            text("""
                SELECT representative_fingerprint_json
                FROM campaigns WHERE id = :id
            """),
            {"id": campaign_id},
        ).fetchone()
        return row[0] if row is not None else None

    def update_campaign_stability(
        self,
        campaign_id: str,
        behavioral_stability_json: str,
    ) -> None:
        """Persist the behavioral stability JSON for a campaign.

        Called by refresh_campaign_stability() after each stability recomputation.
        The column is derived data — fingerprint_history is the authoritative source.
        """
        self._session.execute(
            text("""
                UPDATE campaigns
                SET behavioral_stability_json = :stability_json
                WHERE id = :campaign_id
            """),
            {
                "campaign_id": campaign_id,
                "stability_json": behavioral_stability_json,
            },
        )

    def get_campaign_stability(self, campaign_id: str) -> str | None:
        """Return behavioral_stability_json for campaign_id, or None if not set."""
        row = self._session.execute(
            text("""
                SELECT behavioral_stability_json
                FROM campaigns WHERE id = :id
            """),
            {"id": campaign_id},
        ).fetchone()
        return row[0] if row is not None else None

    def list_campaigns_missing_stability(self) -> list[str]:
        """Return campaign_ids where behavioral_stability_json is NULL.

        Used for batch refresh of campaigns that have not yet been scored.
        """
        rows = self._session.execute(text("""
                SELECT id FROM campaigns
                WHERE behavioral_stability_json IS NULL
                ORDER BY last_seen DESC
            """)).fetchall()
        return [r[0] for r in rows]

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

    def list_campaigns(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return campaigns sorted by last_seen DESC."""
        rows = self._session.execute(
            text("""
                SELECT id, name, status, confidence,
                       first_seen, last_seen, dormant_since,
                       reactivation_count, member_ip_count,
                       attack_tactic_dist, top_target_ports, notes,
                       created_at, updated_at, behavioral_stability_json
                FROM campaigns
                ORDER BY last_seen DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "status": r[2],
                "confidence": r[3],
                "first_seen": r[4],
                "last_seen": r[5],
                "dormant_since": r[6],
                "reactivation_count": r[7],
                "member_ip_count": r[8],
                "attack_tactic_dist": r[9],
                "top_target_ports": r[10],
                "notes": r[11],
                "created_at": r[12],
                "updated_at": r[13],
                "behavioral_stability_json": r[14],
            }
            for r in rows
        ]

    def get_campaign_members(self, campaign_id: str) -> list[dict[str, Any]]:
        """Return all members of a campaign ordered by last_active DESC."""
        rows = self._session.execute(
            text("""
                SELECT campaign_id, source_ip, confidence, added_at, last_active
                FROM campaign_members
                WHERE campaign_id = :campaign_id
                ORDER BY last_active DESC
            """),
            {"campaign_id": campaign_id},
        ).fetchall()
        return [
            {
                "campaign_id": r[0],
                "source_ip": r[1],
                "confidence": r[2],
                "added_at": r[3],
                "last_active": r[4],
            }
            for r in rows
        ]

    def get_campaigns_for_export(self) -> list[dict[str, Any]]:
        """Return non-historical campaigns for STIX export (active/dormant/reactivated)."""
        rows = self._session.execute(
            text("""
                SELECT id, name, status, confidence,
                       first_seen, last_seen, reactivation_count, member_ip_count
                FROM campaigns
                WHERE status IN ('active', 'dormant', 'reactivated')
                ORDER BY last_seen DESC
            """),
        ).fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "status": r[2],
                "confidence": r[3],
                "first_seen": r[4],
                "last_seen": r[5],
                "reactivation_count": r[6],
                "member_ip_count": r[7],
            }
            for r in rows
        ]

    def get_campaign_member_ip_map(self) -> dict[str, str]:
        """Return {source_ip: campaign_id} for all members of non-historical campaigns."""
        rows = self._session.execute(
            text("""
                SELECT cm.source_ip, cm.campaign_id
                FROM campaign_members cm
                JOIN campaigns c ON c.id = cm.campaign_id
                WHERE c.status IN ('active', 'dormant', 'reactivated')
            """),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def transition_active_to_dormant(
        self,
        last_seen_cutoff: str,
        dormant_since: str,
        updated_at: str,
    ) -> int:
        """Move active/reactivated campaigns to dormant.

        Campaigns whose last_seen is older than last_seen_cutoff are transitioned.
        dormant_since is set to the provided timestamp (typically now).

        Returns the number of rows updated.
        """
        result = self._session.execute(
            text("""
                UPDATE campaigns
                SET status = 'dormant',
                    dormant_since = :dormant_since,
                    updated_at = :updated_at
                WHERE status IN ('active', 'reactivated')
                  AND last_seen < :last_seen_cutoff
            """),
            {
                "last_seen_cutoff": last_seen_cutoff,
                "dormant_since": dormant_since,
                "updated_at": updated_at,
            },
        )
        return result.rowcount

    def transition_dormant_to_historical(
        self,
        dormant_since_cutoff: str,
        updated_at: str,
    ) -> int:
        """Move dormant campaigns to historical.

        Campaigns that have had dormant_since set for longer than
        dormant_since_cutoff are transitioned. dormant_since is preserved
        to retain the record of when the campaign entered dormancy.

        Returns the number of rows updated.
        """
        result = self._session.execute(
            text("""
                UPDATE campaigns
                SET status = 'historical',
                    updated_at = :updated_at
                WHERE status = 'dormant'
                  AND dormant_since IS NOT NULL
                  AND dormant_since < :dormant_since_cutoff
            """),
            {
                "dormant_since_cutoff": dormant_since_cutoff,
                "updated_at": updated_at,
            },
        )
        return result.rowcount

    def list_all_campaign_ids(self) -> list[str]:
        """Return all campaign IDs (all statuses)."""
        rows = self._session.execute(text("SELECT id FROM campaigns")).fetchall()
        return [r[0] for r in rows]

    def compute_campaign_attack_tactic_dist(self, campaign_id: str) -> dict[str, int]:
        """Aggregate ATT&CK tactic event counts for all members of a campaign.

        Joins campaign_members → events → event_types to count events per tactic.
        Tactics that are NULL in event_types are excluded.
        Returns {} when the campaign has no members or no matching events.
        """
        rows = self._session.execute(
            text("""
                SELECT et.attack_tactic, COUNT(*) AS event_count
                FROM events e
                JOIN campaign_members cm ON cm.source_ip = e.src_ip
                JOIN event_types et ON et.id = e.event_type
                WHERE cm.campaign_id = :campaign_id
                  AND et.attack_tactic IS NOT NULL
                GROUP BY et.attack_tactic
                ORDER BY event_count DESC
            """),
            {"campaign_id": campaign_id},
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def compute_campaign_top_target_ports(
        self, campaign_id: str, top_n: int = 5
    ) -> list[dict[str, int]]:
        """Aggregate top target ports by event count for all members of a campaign.

        Joins campaign_members → events and groups by dst_port.
        NULL dst_port values are excluded.
        Returns [] when the campaign has no members or no port data.
        """
        rows = self._session.execute(
            text("""
                SELECT e.dst_port, COUNT(*) AS event_count
                FROM events e
                JOIN campaign_members cm ON cm.source_ip = e.src_ip
                WHERE cm.campaign_id = :campaign_id
                  AND e.dst_port IS NOT NULL
                GROUP BY e.dst_port
                ORDER BY event_count DESC
                LIMIT :top_n
            """),
            {"campaign_id": campaign_id, "top_n": top_n},
        ).fetchall()
        return [{"port": r[0], "count": r[1]} for r in rows]

    def update_campaign_analytics(
        self,
        campaign_id: str,
        attack_tactic_dist: str | None,
        top_target_ports: str | None,
        updated_at: str,
    ) -> None:
        """Persist pre-computed analytics JSON strings to the campaigns row."""
        self._session.execute(
            text("""
                UPDATE campaigns
                SET attack_tactic_dist = :attack_tactic_dist,
                    top_target_ports = :top_target_ports,
                    updated_at = :updated_at
                WHERE id = :campaign_id
            """),
            {
                "campaign_id": campaign_id,
                "attack_tactic_dist": attack_tactic_dist,
                "top_target_ports": top_target_ports,
                "updated_at": updated_at,
            },
        )

    def get_campaign_observations(self, campaign_id: str) -> list[dict[str, Any]]:
        """Return all observations for a campaign, ordered by observed_at."""
        rows = self._session.execute(
            text("""
                SELECT id, campaign_id, source_ip, observed_at, event_count,
                       is_reactivation, dormancy_gap_days, notes, analyst_review_json
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
                "analyst_review_json": r[8],
            }
            for r in rows
        ]

    def get_campaign_observation(self, observation_id: str) -> dict[str, Any] | None:
        """Return a single campaign_observations row as dict, or None if not found."""
        row = self._session.execute(
            text("""
                SELECT id, campaign_id, source_ip, observed_at, event_count,
                       is_reactivation, dormancy_gap_days, notes, analyst_review_json
                FROM campaign_observations
                WHERE id = :id
            """),
            {"id": observation_id},
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "campaign_id": row[1],
            "source_ip": row[2],
            "observed_at": row[3],
            "event_count": row[4],
            "is_reactivation": bool(row[5]),
            "dormancy_gap_days": row[6],
            "notes": row[7],
            "analyst_review_json": row[8],
        }

    def list_uncertain_observations(
        self,
        *,
        campaign_id: str | None = None,
        include_reviewed: bool = False,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return uncertain-association observations from campaign_observations.

        Uncertain observations are those whose notes JSON contains
        "decision":"uncertain_association".  SQL pre-filters with LIKE, then
        Python-side parsing confirms (no json_extract per PostgreSQL compat rules).

        When include_reviewed=False (default), only rows where
        analyst_review_json IS NULL are returned.
        """
        params: dict[str, Any] = {"limit": limit}
        cid_clause = ""
        if campaign_id is not None:
            params["campaign_id"] = campaign_id
            cid_clause = "AND campaign_id = :campaign_id"

        review_clause = "" if include_reviewed else "AND analyst_review_json IS NULL"

        rows = self._session.execute(
            text(f"""
                SELECT id, campaign_id, source_ip, observed_at, event_count,
                       is_reactivation, dormancy_gap_days, notes, analyst_review_json
                FROM campaign_observations
                WHERE notes LIKE '%"decision":"uncertain_association"%'
                {cid_clause}
                {review_clause}
                ORDER BY observed_at ASC
                LIMIT :limit
            """),
            params,
        ).fetchall()

        result = []
        for r in rows:
            try:
                parsed = json.loads(r[7]) if r[7] else {}
                if not isinstance(parsed, dict):
                    continue
            except (json.JSONDecodeError, TypeError):
                continue
            if parsed.get("decision") != "uncertain_association":
                continue
            result.append(
                {
                    "id": r[0],
                    "campaign_id": r[1],
                    "source_ip": r[2],
                    "observed_at": r[3],
                    "event_count": r[4],
                    "is_reactivation": bool(r[5]),
                    "dormancy_gap_days": r[6],
                    "notes": r[7],
                    "analyst_review_json": r[8],
                }
            )
        return result

    def list_sparse_campaigns(self, *, limit: int = 200) -> list[dict[str, Any]]:
        """Return campaigns that have no representative fingerprint, newest first.

        These campaigns are sparse: the analytics job has not yet produced a
        representative fingerprint, so behavioral stability and clustering
        candidate comparisons are not available.  Returns full campaign rows
        for operator visibility.  No schema changes — this is a query-time label.
        """
        rows = self._session.execute(
            text("""
                SELECT id, name, status, confidence,
                       first_seen, last_seen, dormant_since,
                       reactivation_count, member_ip_count,
                       attack_tactic_dist, top_target_ports, notes,
                       created_at, updated_at, behavioral_stability_json
                FROM campaigns
                WHERE representative_fingerprint_json IS NULL
                ORDER BY last_seen DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "status": r[2],
                "confidence": r[3],
                "first_seen": r[4],
                "last_seen": r[5],
                "dormant_since": r[6],
                "reactivation_count": r[7],
                "member_ip_count": r[8],
                "attack_tactic_dist": r[9],
                "top_target_ports": r[10],
                "notes": r[11],
                "created_at": r[12],
                "updated_at": r[13],
                "behavioral_stability_json": r[14],
                "has_fingerprint": False,
            }
            for r in rows
        ]

    def get_campaign_observation_counts(self, campaign_id: str) -> dict[str, int]:
        """Return observation_count and review_count for a single campaign."""
        row = self._session.execute(
            text("""
                SELECT COUNT(*) AS obs_count,
                       COUNT(analyst_review_json) AS review_count
                FROM campaign_observations
                WHERE campaign_id = :campaign_id
            """),
            {"campaign_id": campaign_id},
        ).fetchone()
        if row is None:
            return {"observation_count": 0, "review_count": 0}
        return {"observation_count": int(row[0]), "review_count": int(row[1])}

    def get_bulk_observation_counts(self, campaign_ids: list[str]) -> dict[str, dict[str, int]]:
        """Return {campaign_id: {observation_count, review_count}} in one query.

        Campaigns not present in campaign_observations are returned with counts
        of zero.  Used to attach density data to list endpoints without N+1 queries.
        """
        if not campaign_ids:
            return {}
        placeholders = ", ".join(f":p{i}" for i in range(len(campaign_ids)))
        params = {f"p{i}": cid for i, cid in enumerate(campaign_ids)}
        rows = self._session.execute(
            text(f"""
                SELECT campaign_id,
                       COUNT(*) AS obs_count,
                       COUNT(analyst_review_json) AS review_count
                FROM campaign_observations
                WHERE campaign_id IN ({placeholders})
                GROUP BY campaign_id
            """),
            params,
        ).fetchall()
        result: dict[str, dict[str, int]] = {
            cid: {"observation_count": 0, "review_count": 0} for cid in campaign_ids
        }
        for cid, obs, rev in rows:
            result[cid] = {"observation_count": int(obs), "review_count": int(rev)}
        return result

    def get_campaign_with_fingerprint(self, campaign_id: str) -> dict[str, Any] | None:
        """Return full campaign row including representative_fingerprint_json.

        Used by the density endpoint where fingerprint presence must be known.
        """
        row = self._session.execute(
            text("""
                SELECT id, name, status, confidence,
                       first_seen, last_seen, dormant_since,
                       reactivation_count, member_ip_count,
                       attack_tactic_dist, top_target_ports, notes,
                       created_at, updated_at, behavioral_stability_json,
                       representative_fingerprint_json
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
            "behavioral_stability_json": row[14],
            "representative_fingerprint_json": row[15],
        }

    def list_campaigns_with_fingerprint_status(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return campaigns sorted by last_seen DESC with has_fingerprint bool.

        Extends list_campaigns() with a lightweight fingerprint presence flag
        without returning the full fingerprint JSON.  Used by the list endpoint
        to attach evidence_quality without a second round-trip.
        """
        rows = self._session.execute(
            text("""
                SELECT id, name, status, confidence,
                       first_seen, last_seen, dormant_since,
                       reactivation_count, member_ip_count,
                       attack_tactic_dist, top_target_ports, notes,
                       created_at, updated_at, behavioral_stability_json,
                       (representative_fingerprint_json IS NOT NULL) AS has_fingerprint
                FROM campaigns
                ORDER BY last_seen DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "status": r[2],
                "confidence": r[3],
                "first_seen": r[4],
                "last_seen": r[5],
                "dormant_since": r[6],
                "reactivation_count": r[7],
                "member_ip_count": r[8],
                "attack_tactic_dist": r[9],
                "top_target_ports": r[10],
                "notes": r[11],
                "created_at": r[12],
                "updated_at": r[13],
                "behavioral_stability_json": r[14],
                "has_fingerprint": bool(r[15]),
            }
            for r in rows
        ]

    def annotate_campaign_observation(
        self,
        observation_id: str,
        analyst_decision: str,
        analyst_notes: str | None,
        reviewed_at: str,
    ) -> None:
        """Write analyst review metadata to a campaign_observations row.

        Does not modify the original clustering decision, campaign membership,
        or any other observation fields.  Idempotent: subsequent calls overwrite
        the previous review.
        """
        review = {
            "decision": analyst_decision,
            "notes": analyst_notes,
            "reviewed_at": reviewed_at,
        }
        self._session.execute(
            text("""
                UPDATE campaign_observations
                SET analyst_review_json = :review_json
                WHERE id = :observation_id
            """),
            {
                "observation_id": observation_id,
                "review_json": json.dumps(review),
            },
        )
