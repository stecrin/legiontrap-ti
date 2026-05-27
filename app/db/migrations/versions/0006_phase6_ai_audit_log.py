"""Phase 6 ai_audit_log table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-27

Creates: ai_audit_log

ai_audit_log records metadata for every AI backend call — and rate-limit
events — for compliance, cost visibility, and operator accountability.

Rules (§9.1):
  - Content is NEVER stored: no prompt text, no response text.
  - Only metadata: who, when, what model, how many bytes, how long, outcome.
  - Append-only: no UPDATE or DELETE methods are exposed by the repository.
  - Separate from the ingest audit_log table so retention policies can differ.

Status values: success | failure | unavailable | disabled | rate_limited
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # ai_audit_log — metadata record for every AI call attempt.
    #
    # job_id:         links to processing_jobs (null for rate-limited events)
    # output_id:      links to ai_outputs (null when no output was produced)
    # triggered_by:   api_key | user:{sub}
    # backend:        claude | ollama | none | mock
    # model_name:     specific model identifier
    # operation_type: campaign_summary | campaign_brief | fingerprint_clustering
    # resource_type:  campaign | null
    # resource_id:    campaign_id | null
    # payload_bytes:  byte count of user_prompt; 0 for non-AI events
    # response_bytes: byte count of raw response; 0 on failure
    # latency_ms:     wall-clock time of backend.generate() call; 0 if not called
    # status:         success | failure | unavailable | disabled | rate_limited
    # error_type:     AIBackendError | AIBackendUnavailableError |
    #                 AIDisabledError | null on success
    # created_at:     when this record was written
    # ------------------------------------------------------------------
    op.create_table(
        "ai_audit_log",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("job_id", sa.Text, nullable=True),
        sa.Column("output_id", sa.Text, nullable=True),
        sa.Column("triggered_by", sa.Text, nullable=True),
        sa.Column("backend", sa.Text, nullable=False),
        sa.Column("model_name", sa.Text, nullable=False),
        sa.Column("operation_type", sa.Text, nullable=False),
        sa.Column("resource_type", sa.Text, nullable=True),
        sa.Column("resource_id", sa.Text, nullable=True),
        sa.Column("payload_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("response_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("error_type", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("idx_ai_audit_log_created_at", "ai_audit_log", ["created_at"])
    op.create_index("idx_ai_audit_log_job_id", "ai_audit_log", ["job_id"])
    op.create_index("idx_ai_audit_log_triggered_by", "ai_audit_log", ["triggered_by"])
    op.create_index("idx_ai_audit_log_status", "ai_audit_log", ["status"])


def downgrade() -> None:
    op.drop_index("idx_ai_audit_log_status", table_name="ai_audit_log")
    op.drop_index("idx_ai_audit_log_triggered_by", table_name="ai_audit_log")
    op.drop_index("idx_ai_audit_log_job_id", table_name="ai_audit_log")
    op.drop_index("idx_ai_audit_log_created_at", table_name="ai_audit_log")
    op.drop_table("ai_audit_log")
