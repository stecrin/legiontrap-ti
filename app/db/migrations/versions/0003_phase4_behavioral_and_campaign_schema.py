"""Phase 4 behavioral memory and campaign intelligence schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-26

Creates: behavioral_fingerprints, campaigns, campaign_members,
         campaign_observations, campaign_tags.

Excluded per Phase 4 risk review:
  - similarity_vectors: deferred; add only when similarity search is a
    measured performance problem, not a theoretical one.
  - campaigns.tags: dual-write risk eliminated by making campaign_tags
    the single authoritative source for all tag data.
  - campaign_observations.fingerprint_delta: no implementable spec exists
    for delta between nested JSON structures; add in a future PR with a
    versioned algorithm definition.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # behavioral_fingerprints — one row per source IP; updated in place
    # on recomputation. JSON columns for feature categories keep the
    # schema stable as the feature set evolves. fingerprint_version
    # allows computation logic to version independently of the table.
    # The UNIQUE constraint on source_ip is intentionally at the DB level
    # only; Phase 6 relaxes it to UNIQUE(source_ip, valid_from) for
    # temporal segmentation without requiring application-layer changes.
    # ------------------------------------------------------------------
    op.create_table(
        "behavioral_fingerprints",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("source_ip", sa.Text, nullable=False),
        sa.Column("fingerprint_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("computed_at", sa.Text, nullable=False),
        sa.Column("event_count_at_computation", sa.Integer, nullable=False),
        sa.Column("timing_features", sa.Text, nullable=True),
        sa.Column("sequence_features", sa.Text, nullable=True),
        sa.Column("protocol_features", sa.Text, nullable=True),
        sa.Column("credential_features", sa.Text, nullable=True),
        sa.Column("target_features", sa.Text, nullable=True),
        sa.Column("tool_signals", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.ForeignKeyConstraint(["source_ip"], ["source_ips.ip"]),
        sa.UniqueConstraint("source_ip", name="uq_behavioral_fingerprints_source_ip"),
    )

    # ------------------------------------------------------------------
    # campaigns — stable UUID identity persists across IP rotation,
    # dormancy, and reactivation. status lifecycle: active / dormant /
    # historical / reactivated. attack_tactic_dist and top_target_ports
    # are denormalized aggregates for fast dashboard rendering; updated
    # on observation addition, not on every event. No tags column here:
    # all tag reads/writes go through campaign_tags exclusively.
    # ------------------------------------------------------------------
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="'active'"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("first_seen", sa.Text, nullable=False),
        sa.Column("last_seen", sa.Text, nullable=False),
        sa.Column("dormant_since", sa.Text, nullable=True),
        sa.Column("reactivation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("member_ip_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attack_tactic_dist", sa.Text, nullable=True),
        sa.Column("top_target_ports", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index("idx_campaigns_status", "campaigns", ["status"])
    op.create_index("idx_campaigns_last_seen", "campaigns", ["last_seen"])

    # ------------------------------------------------------------------
    # campaign_members — associates source IPs with campaigns. Composite
    # PK enforces the Phase 4 invariant: one campaign per IP. confidence
    # records the fingerprint similarity score that triggered attribution.
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_members",
        sa.Column("campaign_id", sa.Text, nullable=False),
        sa.Column("source_ip", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("added_at", sa.Text, nullable=False),
        sa.Column("last_active", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["source_ip"], ["source_ips.ip"]),
        sa.PrimaryKeyConstraint("campaign_id", "source_ip", name="pk_campaign_members"),
    )
    op.create_index("idx_campaign_members_source_ip", "campaign_members", ["source_ip"])

    # ------------------------------------------------------------------
    # campaign_observations — time-series of campaign activity points.
    # One row per: new IP added, reactivation, or event-count threshold
    # crossed. dormancy_gap_days is populated only on reactivation rows
    # and is the primary input for dormancy pattern analysis.
    # fingerprint_delta is intentionally absent: see module docstring.
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_observations",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("campaign_id", sa.Text, nullable=False),
        sa.Column("source_ip", sa.Text, nullable=False),
        sa.Column("observed_at", sa.Text, nullable=False),
        sa.Column("event_count", sa.Integer, nullable=False),
        sa.Column("is_reactivation", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dormancy_gap_days", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
    )
    op.create_index(
        "idx_campaign_observations_campaign",
        "campaign_observations",
        ["campaign_id", "observed_at"],
    )

    # ------------------------------------------------------------------
    # campaign_tags — single authoritative source for campaign tags.
    # source distinguishes operator-applied tags ('manual') from
    # system-generated tags ('auto'). The campaigns table has no tags
    # column; dual-write divergence is eliminated by design.
    # ------------------------------------------------------------------
    op.create_table(
        "campaign_tags",
        sa.Column("campaign_id", sa.Text, nullable=False),
        sa.Column("tag", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False, server_default="'auto'"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("campaign_id", "tag", name="pk_campaign_tags"),
    )


def downgrade() -> None:
    op.drop_table("campaign_tags")
    op.drop_index("idx_campaign_observations_campaign", table_name="campaign_observations")
    op.drop_table("campaign_observations")
    op.drop_index("idx_campaign_members_source_ip", table_name="campaign_members")
    op.drop_table("campaign_members")
    op.drop_index("idx_campaigns_last_seen", table_name="campaigns")
    op.drop_index("idx_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_table("behavioral_fingerprints")
