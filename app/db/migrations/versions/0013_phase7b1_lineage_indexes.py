"""Phase 7 Group B1 — campaign_lineage indexes.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-29

The Phase 6 Group D migration (0010) created campaign_lineage without
indexes.  This migration adds the two indexes referenced in the Phase 7
blueprint §8:

  idx_lineage_actor    on actor_profile_id  — powers GET /api/actors/{id}/campaigns
  idx_lineage_campaign on campaign_id       — powers GET /api/campaigns/{id}/actors

No table changes.  No data changes.  Index-only migration.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("idx_lineage_actor", "campaign_lineage", ["actor_profile_id"])
    op.create_index("idx_lineage_campaign", "campaign_lineage", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("idx_lineage_campaign", table_name="campaign_lineage")
    op.drop_index("idx_lineage_actor", table_name="campaign_lineage")
