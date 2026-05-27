"""Phase 6 processing_jobs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-27

Creates: processing_jobs

processing_jobs is the central coordination table for all async operations.
It serves three purposes simultaneously:
  - Async AI execution tracking (campaign_summary, campaign_brief jobs)
  - Clustering deduplication (replaces the _pending in-memory set)
  - Future rate-limiting state

Status lifecycle: pending → running → completed | failed | cancelled

Deduplication semantics: a non-null deduplication_key prevents a second job
from being created while an identical job is pending or running. Enforced at
the application layer (get_active_job_by_dedup_key before create_job).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # processing_jobs — persistent async job coordination table.
    #
    # job_type values: campaign_summary | campaign_brief |
    #                  fingerprint_clustering
    # status values:   pending | running | completed | failed | cancelled
    #
    # result_summary_json holds the full result for terminal jobs.
    # In Phase 6 PR A2 this will be superseded by ai_outputs; for A1 it
    # is the authoritative result store.
    #
    # backend_metadata_json stores non-content execution metadata:
    # {"ai_backend": "mock", "latency_ms": 0}. Never stores prompt or
    # response content.
    # ------------------------------------------------------------------
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("job_type", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="'pending'"),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("started_at", sa.Text, nullable=True),
        sa.Column("completed_at", sa.Text, nullable=True),
        sa.Column("failed_at", sa.Text, nullable=True),
        sa.Column("triggered_by", sa.Text, nullable=True),
        sa.Column("resource_type", sa.Text, nullable=True),
        sa.Column("resource_id", sa.Text, nullable=True),
        sa.Column("deduplication_key", sa.Text, nullable=True),
        sa.Column("progress_percent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("result_summary_json", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("backend_metadata_json", sa.Text, nullable=True),
    )
    op.create_index("idx_processing_jobs_status", "processing_jobs", ["status"])
    op.create_index("idx_processing_jobs_dedup_key", "processing_jobs", ["deduplication_key"])
    op.create_index(
        "idx_processing_jobs_resource", "processing_jobs", ["resource_type", "resource_id"]
    )
    op.create_index("idx_processing_jobs_created_at", "processing_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_processing_jobs_created_at", table_name="processing_jobs")
    op.drop_index("idx_processing_jobs_resource", table_name="processing_jobs")
    op.drop_index("idx_processing_jobs_dedup_key", table_name="processing_jobs")
    op.drop_index("idx_processing_jobs_status", table_name="processing_jobs")
    op.drop_table("processing_jobs")
