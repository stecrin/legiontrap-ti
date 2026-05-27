"""Phase 6 Group B — analyst review state for uncertain campaign observations

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-27

Adds analyst_review_json to campaign_observations.

analyst_review_json stores the analyst's interpretation of an uncertain
association observation as a JSON object:
  {
    "decision": "analyst_confirmed" | "analyst_denied",
    "notes": str | null,
    "reviewed_at": str (ISO timestamp)
  }

This is analyst-supplied metadata, not a mutation of the original clustering
decision.  The observation record and campaign membership are never modified
by a review.  NULL until an analyst submits a review for the observation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaign_observations",
        sa.Column("analyst_review_json", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_observations", "analyst_review_json")
