"""Phase 7 Group A — behavioral drift alerts.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-29

Creates behavioral_alerts.

One row per drift threshold crossing.  The alert generation job inserts a row
when a campaign's behavioral stability falls below a configured threshold.

Deduplication: the job never inserts a new alert when an existing unacknowledged
alert for the same (campaign_id, dimension) pair already exists.  NULL dimension
is used for composite alerts.

Acknowledged alerts (acknowledged_at IS NOT NULL) do not block new alerts from
firing if the stability score crosses the threshold again after acknowledgement.

alert_type values: composite_drift | dimension_drift
dimension values: NULL (composite) | timing | sequence | protocol | credential | target

Alerts are informational only.  No code path mutates campaigns, fingerprints,
or clustering decisions in response to an alert.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "behavioral_alerts",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("campaign_id", sa.Text, nullable=False),
        sa.Column("alert_type", sa.Text, nullable=False),
        sa.Column("dimension", sa.Text, nullable=True),
        sa.Column("threshold_configured", sa.Real, nullable=False),
        sa.Column("observed_value", sa.Real, nullable=False),
        sa.Column("stability_snapshot_json", sa.Text, nullable=False),
        sa.Column("triggered_at", sa.Text, nullable=False),
        sa.Column("acknowledged_at", sa.Text, nullable=True),
        sa.Column("acknowledged_notes", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
    )
    op.create_index("idx_alerts_campaign", "behavioral_alerts", ["campaign_id"])
    op.create_index("idx_alerts_triggered", "behavioral_alerts", ["triggered_at"])
    op.create_index("idx_alerts_acknowledged", "behavioral_alerts", ["acknowledged_at"])


def downgrade() -> None:
    op.drop_index("idx_alerts_acknowledged", table_name="behavioral_alerts")
    op.drop_index("idx_alerts_triggered", table_name="behavioral_alerts")
    op.drop_index("idx_alerts_campaign", table_name="behavioral_alerts")
    op.drop_table("behavioral_alerts")
