"""Phase 6 Group B — fingerprint history and campaign representative fingerprint

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-27

Creates: fingerprint_history
Alters:  campaigns — adds representative_fingerprint_json column

fingerprint_history is an append-only longitudinal record of every computed
fingerprint snapshot.  The behavioral_fingerprints table retains only the
current (latest) fingerprint per IP; fingerprint_history accumulates the
full history for metamorphic detection and behavioral stability analysis
(§11.2, §11.3 of the Phase 6 blueprint).

representative_fingerprint_json on campaigns is a denormalized cache of the
most-recently-active member's fingerprint features, stored to eliminate the
O(n) per-campaign member → fingerprint lookups in the clustering candidate
query (§13.2).  It is derived from behavioral_fingerprints; behavioral_fingerprints
remains the authoritative source.

Rules:
  - fingerprint_history is append-only: no UPDATE or DELETE methods.
  - representative_fingerprint_json is updated after each fingerprint
    computation that results in a campaign assignment.
  - No raw credentials or raw payloads are stored in fingerprint_history.
    Feature columns store statistical summaries and distributions only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # fingerprint_history — longitudinal fingerprint snapshot table.
    #
    # fingerprint_id:             FK to behavioral_fingerprints.id at the time
    #                             of computation; NULL when IP is new and the
    #                             fingerprints row was just inserted.
    # source_ip:                  The IP whose fingerprint was computed.
    # campaign_id:                The campaign the IP was associated with at
    #                             computation time; NULL for new IPs before
    #                             clustering assigns them.
    # fingerprint_version:        Schema version of the feature encoding (§12.1).
    # computed_at:                When the fingerprint computation ran.
    # event_count_at_computation: Number of events used in this computation.
    # confidence:                 The fingerprint confidence at this snapshot.
    # timing_features:            JSON feature dict at this snapshot (no raw events).
    # sequence_features:          JSON feature dict (port/event sequences).
    # protocol_features:          JSON feature dict (TLS/SSH/HTTP signals).
    # credential_features:        JSON feature dict (patterns only, no raw creds).
    # target_features:            JSON feature dict (port distributions).
    # created_at:                 When this history record was written.
    # ------------------------------------------------------------------
    op.create_table(
        "fingerprint_history",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("fingerprint_id", sa.Text, nullable=True),
        sa.Column("source_ip", sa.Text, nullable=False),
        sa.Column("campaign_id", sa.Text, nullable=True),
        sa.Column("fingerprint_version", sa.Integer, nullable=False),
        sa.Column("computed_at", sa.Text, nullable=False),
        sa.Column("event_count_at_computation", sa.Integer, nullable=False),
        sa.Column("confidence", sa.Real, nullable=False),
        sa.Column("timing_features", sa.Text, nullable=True),
        sa.Column("sequence_features", sa.Text, nullable=True),
        sa.Column("protocol_features", sa.Text, nullable=True),
        sa.Column("credential_features", sa.Text, nullable=True),
        sa.Column("target_features", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("idx_fingerprint_history_source_ip", "fingerprint_history", ["source_ip"])
    op.create_index("idx_fingerprint_history_campaign_id", "fingerprint_history", ["campaign_id"])
    op.create_index("idx_fingerprint_history_computed_at", "fingerprint_history", ["computed_at"])
    op.create_index(
        "idx_fingerprint_history_fingerprint_id",
        "fingerprint_history",
        ["fingerprint_id"],
    )

    # ------------------------------------------------------------------
    # campaigns.representative_fingerprint_json — denormalized cache.
    #
    # Stores the fingerprint features of the most-recently-active campaign
    # member, serialised as a JSON object.  Populated after each successful
    # fingerprint computation → clustering assignment.  NULL until first
    # assignment.  Always a cache; behavioral_fingerprints is authoritative.
    # ------------------------------------------------------------------
    op.add_column(
        "campaigns",
        sa.Column("representative_fingerprint_json", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "representative_fingerprint_json")

    op.drop_index("idx_fingerprint_history_fingerprint_id", table_name="fingerprint_history")
    op.drop_index("idx_fingerprint_history_computed_at", table_name="fingerprint_history")
    op.drop_index("idx_fingerprint_history_campaign_id", table_name="fingerprint_history")
    op.drop_index("idx_fingerprint_history_source_ip", table_name="fingerprint_history")
    op.drop_table("fingerprint_history")
