"""Phase 2E intelligence query indexes

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-25

Adds two indexes identified by the Phase 2E schema readiness audit:

  idx_source_ips_reputation — supports list_source_ips ORDER BY reputation_score DESC
  idx_events_src_ip_type    — covering index for get_source_ip_event_types
                              (SELECT DISTINCT event_type FROM events WHERE src_ip = :ip)

The source_ips(tags) partial JSON index is deferred: SQLite json_each expression
indexes require careful quoting and offer diminishing returns until tag-filtered
queries are confirmed in production workloads.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_source_ips_reputation",
        "source_ips",
        [sa.text("reputation_score DESC")],
    )
    op.create_index(
        "idx_events_src_ip_type",
        "events",
        ["src_ip", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_events_src_ip_type", table_name="events")
    op.drop_index("idx_source_ips_reputation", table_name="source_ips")
