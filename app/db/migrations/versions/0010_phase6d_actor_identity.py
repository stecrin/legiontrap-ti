"""Phase 6 Group D — actor identity schema foundations.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-28

Creates two empty schema foundations for Phase 7 actor-level intelligence:

  actor_profiles  — one row per inferred actor identity. Populated only by
                    explicit operator or future automated assignment.  No row
                    is created automatically during clustering or campaign
                    lifecycle transitions.

  campaign_lineage — links a campaign to an actor_profile with an explicit
                     relationship_type and analyst-supplied evidence.  Does not
                     mutate campaign membership, clustering decisions, or any
                     existing table.

Intentionally absent in this migration:
  - No automatic actor attribution logic
  - No campaign merging or splitting
  - No AI actor naming
  - No federation endpoints
  - No API endpoints (deferred to Phase 7)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "actor_profiles",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("confidence", sa.Real, nullable=False, server_default="0.5"),
        sa.Column("status", sa.Text, nullable=False, server_default="'active'"),
        sa.Column("representative_fingerprint_json", sa.Text, nullable=True),
        sa.Column("behavioral_stability_json", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_table(
        "campaign_lineage",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("actor_profile_id", sa.Text, nullable=False),
        sa.Column("campaign_id", sa.Text, nullable=False),
        sa.Column("relationship_type", sa.Text, nullable=False),
        sa.Column("confidence", sa.Real, nullable=False, server_default="0.5"),
        sa.Column("evidence_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["actor_profile_id"], ["actor_profiles.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
    )


def downgrade() -> None:
    op.drop_table("campaign_lineage")
    op.drop_table("actor_profiles")
