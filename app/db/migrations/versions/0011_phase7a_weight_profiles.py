"""Phase 7 Group A — per-campaign similarity weight profiles.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29

Creates campaign_weight_profiles.

One row per campaign.  Written only after WEIGHT_PROFILE_MIN_REVIEWS analyst
reviews have been processed for that campaign.  Until a row exists, the
campaign uses global default weights from settings.

adjustment_log_json is an append-only JSON array.  Each entry records:
  - observation_id: the source campaign_observations row
  - review_decision: analyst_confirmed | analyst_denied
  - reviewed_at: ISO timestamp from the source review
  - dimension_adjustments: per-dimension nudge applied
  - weights_after: the weights resulting from this adjustment

Weight adjustments are bounded by WEIGHT_FLOOR and WEIGHT_CEILING env vars.
The review job is idempotent: observation IDs already present in the log
are never re-applied.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_weight_profiles",
        sa.Column("campaign_id", sa.Text, primary_key=True),
        sa.Column("weight_timing", sa.Real, nullable=False),
        sa.Column("weight_sequence", sa.Real, nullable=False),
        sa.Column("weight_protocol", sa.Real, nullable=False),
        sa.Column("weight_credential", sa.Real, nullable=False),
        sa.Column("weight_target", sa.Real, nullable=False),
        sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("confirmed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("denied_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("adjustment_log_json", sa.Text, nullable=False, server_default="'[]'"),
        sa.Column("computed_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
    )


def downgrade() -> None:
    op.drop_table("campaign_weight_profiles")
