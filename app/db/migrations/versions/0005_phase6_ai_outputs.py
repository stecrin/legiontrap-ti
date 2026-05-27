"""Phase 6 ai_outputs table and ai_output_id on processing_jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-27

Creates: ai_outputs
Alters:  processing_jobs — adds ai_output_id column

ai_outputs is an immutable provenance record for every AI-generated artifact.
Write-once semantics enforced at the application layer (no UPDATE path).
Corrections create new rows; old rows are never modified.

Columns align with §8.2 of the Phase 6 blueprint, using the resource_type /
resource_id pattern for consistency with processing_jobs.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # ai_outputs — immutable AI-generated artifact records.
    #
    # output_type:         campaign_summary | campaign_brief
    # resource_type:       campaign (summaries) | null (briefs)
    # resource_id:         campaign_id (summaries) | null (briefs)
    # content:             AI text; null when rejected=1
    # backend:             claude | ollama | none | mock
    # model_name:          the specific model identifier (indexed)
    # prompt_hash:         SHA-256 of user_prompt; no prompt content stored
    # payload_bytes:       byte count of user_prompt for audit
    # source_records_json: provenance metadata snapshot at generation time
    # safety_flags_json:   flags from prompt_builder (e.g. low_confidence)
    # rejected:            1 when output failed safety validation
    # rejection_reason:    ip_detected | empty_response | null
    # truncated:           1 when output was cut to the length limit
    # data_quality_score:  composite score from confidence/obs/fp completeness
    # generated_at:        when the AI call completed (not when job was created)
    # triggered_by:        api_key | user:{sub} | system:ingest
    # ------------------------------------------------------------------
    op.create_table(
        "ai_outputs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("job_id", sa.Text, nullable=False),
        sa.Column("output_type", sa.Text, nullable=False),
        sa.Column("resource_type", sa.Text, nullable=True),
        sa.Column("resource_id", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("backend", sa.Text, nullable=False),
        sa.Column("model_name", sa.Text, nullable=False),
        sa.Column("prompt_hash", sa.Text, nullable=False),
        sa.Column("payload_bytes", sa.Integer, nullable=False),
        sa.Column("source_records_json", sa.Text, nullable=False),
        sa.Column("safety_flags_json", sa.Text, nullable=True),
        sa.Column("rejected", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("truncated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("data_quality_score", sa.Real, nullable=True),
        sa.Column("generated_at", sa.Text, nullable=False),
        sa.Column("triggered_by", sa.Text, nullable=True),
    )
    op.create_index("idx_ai_outputs_job_id", "ai_outputs", ["job_id"])
    op.create_index("idx_ai_outputs_resource", "ai_outputs", ["resource_type", "resource_id"])
    op.create_index("idx_ai_outputs_generated_at", "ai_outputs", ["generated_at"])
    op.create_index("idx_ai_outputs_model_name", "ai_outputs", ["model_name"])

    # Add ai_output_id to processing_jobs so the polling endpoint can expose it.
    op.add_column("processing_jobs", sa.Column("ai_output_id", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_index("idx_ai_outputs_model_name", table_name="ai_outputs")
    op.drop_index("idx_ai_outputs_generated_at", table_name="ai_outputs")
    op.drop_index("idx_ai_outputs_resource", table_name="ai_outputs")
    op.drop_index("idx_ai_outputs_job_id", table_name="ai_outputs")
    op.drop_table("ai_outputs")
    op.drop_column("processing_jobs", "ai_output_id")
