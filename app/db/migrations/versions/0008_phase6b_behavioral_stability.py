"""Phase 6 Group B — behavioral stability score column on campaigns

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-27

Adds behavioral_stability_json to campaigns.

behavioral_stability_json stores the most-recently-computed stability
assessment for a campaign as a JSON object:
  {
    "status": "ok" | "insufficient_data",
    "composite_score": float,          -- weighted average of per-dimension scores
    "timing_stability": float | null,
    "sequence_stability": float | null,
    "protocol_stability": float | null,
    "credential_stability": float | null,
    "target_stability": float | null,
    "sample_count": int,               -- history records used
    "pair_count": int,                 -- consecutive pairs evaluated
    "dimensions_used": int,
    "calculated_at": str,
    "explanation": {...}               -- per-dimension breakdown
  }

This is derived data, not source of truth.  fingerprint_history is the
authoritative record.  The column is recomputed after each fingerprint
history append and can be reconstructed at any time from fingerprint_history.

NULL until the first fingerprint history computation for a campaign member
produces at least two history records.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("behavioral_stability_json", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "behavioral_stability_json")
