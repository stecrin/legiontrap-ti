"""Actor identity repository — Phase 6 Group D schema foundations.

Read/write methods for actor_profiles and campaign_lineage tables.

These tables are empty scaffolding created in Phase 6 to prepare Phase 7
actor-level intelligence without implementing actor attribution yet.

Invariants:
  - No method here performs automatic actor attribution.
  - No method here merges or splits campaigns.
  - No method here reads from or writes to the clustering path.
  - campaign_lineage records are created only by explicit operator or future
    Phase 7 automation — never by clustering.py or any existing job runner.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.repositories._base import RepositoryBase
from app.intelligence.actor_constants import VALID_RELATIONSHIP_TYPES

_UNSET = object()


def _actor_row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "display_name": row[1],
        "confidence": row[2],
        "status": row[3],
        "representative_fingerprint_json": row[4],
        "behavioral_stability_json": row[5],
        "notes": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


def _lineage_row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "actor_profile_id": row[1],
        "campaign_id": row[2],
        "relationship_type": row[3],
        "confidence": row[4],
        "evidence_json": row[5],
        "created_at": row[6],
    }


_ACTOR_SELECT = """
    SELECT id, display_name, confidence, status,
           representative_fingerprint_json, behavioral_stability_json,
           notes, created_at, updated_at
    FROM actor_profiles
"""

_LINEAGE_SELECT = """
    SELECT id, actor_profile_id, campaign_id, relationship_type,
           confidence, evidence_json, created_at
    FROM campaign_lineage
"""


class ActorRepository(RepositoryBase):
    def create_actor_profile(
        self,
        *,
        actor_id: str | None = None,
        display_name: str,
        confidence: float = 0.5,
        status: str = "active",
        representative_fingerprint_json: dict | str | None = None,
        behavioral_stability_json: dict | str | None = None,
        notes: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new actor_profile row and return it.

        actor_id is caller-generated or auto-assigned as UUID4.
        No automatic actor attribution occurs here or downstream.
        """
        aid = actor_id or str(uuid.uuid4())
        now = created_at or datetime.now(UTC).isoformat()
        updated = updated_at or now

        rep_fp = (
            json.dumps(representative_fingerprint_json)
            if isinstance(representative_fingerprint_json, dict)
            else representative_fingerprint_json
        )
        beh_stab = (
            json.dumps(behavioral_stability_json)
            if isinstance(behavioral_stability_json, dict)
            else behavioral_stability_json
        )

        self._session.execute(
            text("""
                INSERT INTO actor_profiles (
                    id, display_name, confidence, status,
                    representative_fingerprint_json, behavioral_stability_json,
                    notes, created_at, updated_at
                ) VALUES (
                    :id, :display_name, :confidence, :status,
                    :representative_fingerprint_json, :behavioral_stability_json,
                    :notes, :created_at, :updated_at
                )
            """),
            {
                "id": aid,
                "display_name": display_name,
                "confidence": confidence,
                "status": status,
                "representative_fingerprint_json": rep_fp,
                "behavioral_stability_json": beh_stab,
                "notes": notes,
                "created_at": now,
                "updated_at": updated,
            },
        )
        return self.get_actor_profile(aid)  # type: ignore[return-value]

    def get_actor_profile(self, actor_id: str) -> dict[str, Any] | None:
        """Return a single actor_profile row by id, or None if not found."""
        row = self._session.execute(
            text(_ACTOR_SELECT + "WHERE id = :id"),
            {"id": actor_id},
        ).fetchone()
        return _actor_row_to_dict(row) if row is not None else None

    def list_actor_profiles(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return actor_profiles ordered by created_at DESC.

        Optionally filtered by status (e.g. 'active', 'archived').
        """
        params: dict[str, Any] = {"limit": limit}
        where = ""
        if status is not None:
            where = "WHERE status = :status "
            params["status"] = status
        rows = self._session.execute(
            text(_ACTOR_SELECT + where + "ORDER BY created_at DESC LIMIT :limit"),
            params,
        ).fetchall()
        return [_actor_row_to_dict(r) for r in rows]

    def update_actor_profile(
        self,
        actor_id: str,
        *,
        display_name: str | None = None,
        notes: str | None = _UNSET,
        confidence: float | None = None,
        status: str | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any] | None:
        """Apply a partial update to an actor_profile row.

        Only non-None / non-sentinel fields are written.  Returns the updated
        row, or None if actor_id is not found.
        """
        now = updated_at or datetime.now(UTC).isoformat()
        assignments: list[str] = ["updated_at = :updated_at"]
        params: dict[str, Any] = {"id": actor_id, "updated_at": now}

        if display_name is not None:
            assignments.append("display_name = :display_name")
            params["display_name"] = display_name
        if notes is not _UNSET:
            assignments.append("notes = :notes")
            params["notes"] = notes
        if confidence is not None:
            assignments.append("confidence = :confidence")
            params["confidence"] = confidence
        if status is not None:
            assignments.append("status = :status")
            params["status"] = status

        self._session.execute(
            text(
                f"UPDATE actor_profiles SET {', '.join(assignments)} WHERE id = :id"
            ),  # noqa: S608
            params,
        )
        return self.get_actor_profile(actor_id)

    def link_campaign_to_actor(
        self,
        *,
        lineage_id: str | None = None,
        actor_profile_id: str,
        campaign_id: str,
        relationship_type: str,
        confidence: float = 0.5,
        evidence_json: dict | str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert a campaign_lineage row linking a campaign to an actor.

        Does not modify campaign membership, clustering decisions, or any
        existing table outside campaign_lineage.

        Raises ValueError for unrecognized relationship_type values.
        """
        if relationship_type not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"Invalid relationship_type {relationship_type!r}. "
                f"Must be one of: {sorted(VALID_RELATIONSHIP_TYPES)}"
            )
        lid = lineage_id or str(uuid.uuid4())
        now = created_at or datetime.now(UTC).isoformat()
        ev_str = json.dumps(evidence_json) if isinstance(evidence_json, dict) else evidence_json

        self._session.execute(
            text("""
                INSERT INTO campaign_lineage (
                    id, actor_profile_id, campaign_id,
                    relationship_type, confidence, evidence_json, created_at
                ) VALUES (
                    :id, :actor_profile_id, :campaign_id,
                    :relationship_type, :confidence, :evidence_json, :created_at
                )
            """),
            {
                "id": lid,
                "actor_profile_id": actor_profile_id,
                "campaign_id": campaign_id,
                "relationship_type": relationship_type,
                "confidence": confidence,
                "evidence_json": ev_str,
                "created_at": now,
            },
        )
        row = self._session.execute(
            text(_LINEAGE_SELECT + "WHERE id = :id"),
            {"id": lid},
        ).fetchone()
        return _lineage_row_to_dict(row)  # type: ignore[arg-type]

    def list_campaign_lineage(
        self,
        *,
        actor_profile_id: str | None = None,
        campaign_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return campaign_lineage rows, newest first.

        Filter by actor_profile_id, campaign_id, or both.
        """
        params: dict[str, Any] = {"limit": limit}
        clauses: list[str] = []
        if actor_profile_id is not None:
            clauses.append("actor_profile_id = :actor_profile_id")
            params["actor_profile_id"] = actor_profile_id
        if campaign_id is not None:
            clauses.append("campaign_id = :campaign_id")
            params["campaign_id"] = campaign_id
        where = ("WHERE " + " AND ".join(clauses) + " ") if clauses else ""
        rows = self._session.execute(
            text(_LINEAGE_SELECT + where + "ORDER BY created_at DESC LIMIT :limit"),
            params,
        ).fetchall()
        return [_lineage_row_to_dict(r) for r in rows]

    def get_lineage_row(self, lineage_id: str) -> dict[str, Any] | None:
        """Return a single campaign_lineage row by id, or None if not found."""
        row = self._session.execute(
            text(_LINEAGE_SELECT + "WHERE id = :id"),
            {"id": lineage_id},
        ).fetchone()
        return _lineage_row_to_dict(row) if row is not None else None

    def delete_lineage_row(self, lineage_id: str) -> None:
        """Hard-delete a single campaign_lineage row by id.

        Raises no error if the row does not exist — callers should check
        get_lineage_row() first to enforce 404 semantics at the router layer.
        Campaigns and actor_profiles are never touched.
        """
        self._session.execute(
            text("DELETE FROM campaign_lineage WHERE id = :id"),
            {"id": lineage_id},
        )

    def list_actor_campaigns_with_metadata(
        self,
        actor_profile_id: str,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return campaigns linked to an actor with campaign metadata.

        JOINs campaign_lineage with campaigns for each linked campaign.
        Ordered by lineage created_at DESC.  Campaigns absent from the
        campaigns table appear with NULL name/status/last_seen fields.
        """
        rows = self._session.execute(
            text("""
                SELECT cl.id, cl.campaign_id, cl.relationship_type, cl.confidence,
                       cl.evidence_json, cl.created_at,
                       c.name, c.status, c.last_seen
                FROM campaign_lineage cl
                LEFT JOIN campaigns c ON cl.campaign_id = c.id
                WHERE cl.actor_profile_id = :actor_profile_id
                ORDER BY cl.created_at DESC
                LIMIT :limit
            """),
            {"actor_profile_id": actor_profile_id, "limit": limit},
        ).fetchall()
        return [
            {
                "lineage_id": row[0],
                "campaign_id": row[1],
                "relationship_type": row[2],
                "confidence": row[3],
                "evidence_json": row[4],
                "linked_at": row[5],
                "campaign_name": row[6],
                "campaign_status": row[7],
                "campaign_last_seen": row[8],
            }
            for row in rows
        ]

    def list_actors_for_campaign(self, campaign_id: str) -> list[dict[str, Any]]:
        """Return actors linked to a campaign with actor profile metadata.

        JOINs campaign_lineage with actor_profiles.
        Ordered by lineage created_at DESC.
        """
        rows = self._session.execute(
            text("""
                SELECT cl.id, cl.actor_profile_id, cl.relationship_type, cl.confidence,
                       cl.evidence_json, cl.created_at,
                       ap.display_name, ap.status, ap.confidence AS actor_confidence
                FROM campaign_lineage cl
                LEFT JOIN actor_profiles ap ON cl.actor_profile_id = ap.id
                WHERE cl.campaign_id = :campaign_id
                ORDER BY cl.created_at DESC
            """),
            {"campaign_id": campaign_id},
        ).fetchall()
        return [
            {
                "lineage_id": row[0],
                "actor_profile_id": row[1],
                "relationship_type": row[2],
                "confidence": row[3],
                "evidence_json": row[4],
                "linked_at": row[5],
                "actor_display_name": row[6],
                "actor_status": row[7],
                "actor_confidence": row[8],
            }
            for row in rows
        ]

    def list_campaigns_for_suggestions(self, *, limit: int = 500) -> list[dict[str, Any]]:
        """Return campaigns eligible for actor suggestion comparison.

        Only campaigns with a non-NULL representative_fingerprint_json and
        status in (active, dormant, reactivated) are returned.  The feature
        columns are extracted from the fingerprint JSON so callers can pass
        the result directly to compute_weighted_similarity.

        Campaigns whose fingerprint JSON cannot be parsed are silently skipped.
        """
        rows = self._session.execute(
            text("""
                SELECT id, name, status, last_seen, member_ip_count,
                       representative_fingerprint_json
                FROM campaigns
                WHERE representative_fingerprint_json IS NOT NULL
                  AND status IN ('active', 'dormant', 'reactivated')
                ORDER BY last_seen DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            cid, name, status, last_seen, member_ip_count, rep_fp_json = row
            try:
                fp_data = json.loads(rep_fp_json)
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue
            results.append(
                {
                    "id": cid,
                    "name": name,
                    "status": status,
                    "last_seen": last_seen,
                    "member_ip_count": member_ip_count,
                    "timing_features": fp_data.get("timing_features"),
                    "sequence_features": fp_data.get("sequence_features"),
                    "protocol_features": fp_data.get("protocol_features"),
                    "credential_features": fp_data.get("credential_features"),
                    "target_features": fp_data.get("target_features"),
                }
            )
        return results

    def list_actor_campaign_stability(
        self,
        actor_profile_id: str,
    ) -> list[dict[str, Any]]:
        """Return stability data for campaigns linked to an actor.

        JOINs campaign_lineage with campaigns to fetch behavioral_stability_json
        alongside lineage metadata.  Campaigns missing from the campaigns table
        (orphaned lineage rows) are included with NULL stability fields — callers
        must handle None values.

        Ordered by lineage created_at ASC so the oldest link appears first.
        """
        rows = self._session.execute(
            text("""
                SELECT cl.campaign_id, cl.relationship_type, cl.confidence,
                       c.name, c.status, c.last_seen,
                       c.behavioral_stability_json
                FROM campaign_lineage cl
                LEFT JOIN campaigns c ON cl.campaign_id = c.id
                WHERE cl.actor_profile_id = :actor_profile_id
                ORDER BY cl.created_at ASC
            """),
            {"actor_profile_id": actor_profile_id},
        ).fetchall()
        return [
            {
                "campaign_id": row[0],
                "relationship_type": row[1],
                "confidence": row[2],
                "campaign_name": row[3],
                "campaign_status": row[4],
                "last_seen": row[5],
                "behavioral_stability_json": row[6],
            }
            for row in rows
        ]

    def get_coattributed_campaign_pairs(self) -> set[frozenset[str]]:
        """Return campaign pairs already linked through a common actor.

        Two campaigns are co-attributed when both appear in campaign_lineage
        under the same actor_profile_id — regardless of relationship_type.
        These pairs are excluded from actor suggestions.
        """
        rows = self._session.execute(
            text(
                "SELECT actor_profile_id, campaign_id"
                " FROM campaign_lineage ORDER BY actor_profile_id"
            ),
        ).fetchall()

        actor_campaigns: dict[str, list[str]] = {}
        for actor_id, campaign_id in rows:
            actor_campaigns.setdefault(actor_id, []).append(campaign_id)

        pairs: set[frozenset[str]] = set()
        for cids in actor_campaigns.values():
            if len(cids) >= 2:
                for i in range(len(cids)):
                    for j in range(i + 1, len(cids)):
                        pairs.add(frozenset({cids[i], cids[j]}))
        return pairs
