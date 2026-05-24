"""initial schema — Phase 1 tables

Revision ID: 0001
Revises:
Create Date: 2026-05-24

Creates: event_types, raw_events, source_ips, events, audit_log.
Behavioral/AI/federation tables are deferred to later phases per DATABASE_SCHEMA.md.
Seeds event_types with the initial ATT&CK-mapped taxonomy.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # event_types — lookup table; created first (events has a FK to it)
    # ------------------------------------------------------------------
    op.create_table(
        "event_types",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("attack_tactic", sa.Text, nullable=True),
        sa.Column("attack_technique", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
    )

    # Initial seed from DATABASE_SCHEMA.md
    op.bulk_insert(
        sa.table(
            "event_types",
            sa.column("id", sa.Text),
            sa.column("label", sa.Text),
            sa.column("attack_tactic", sa.Text),
            sa.column("attack_technique", sa.Text),
        ),
        [
            {
                "id": "auth_failed",
                "label": "SSH Authentication Failure",
                "attack_tactic": "Credential Access",
                "attack_technique": "T1110.001",
            },
            {
                "id": "auth_success",
                "label": "SSH Authentication Success",
                "attack_tactic": "Initial Access",
                "attack_technique": "T1078",
            },
            {
                "id": "port_scan",
                "label": "Port Scan Probe",
                "attack_tactic": "Discovery",
                "attack_technique": "T1046",
            },
            {
                "id": "http_probe",
                "label": "HTTP Endpoint Probe",
                "attack_tactic": "Discovery",
                "attack_technique": "T1595.002",
            },
            {
                "id": "malware_upload",
                "label": "Malware Upload Attempt",
                "attack_tactic": "Execution",
                "attack_technique": "T1204",
            },
            {
                "id": "command_exec",
                "label": "Remote Command Execution",
                "attack_tactic": "Execution",
                "attack_technique": "T1059",
            },
            {
                "id": "unknown",
                "label": "Unknown Event Type",
                "attack_tactic": None,
                "attack_technique": None,
            },
        ],
    )

    # ------------------------------------------------------------------
    # raw_events — immutable provenance; no FK dependencies
    # ------------------------------------------------------------------
    op.create_table(
        "raw_events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("ts", sa.Text, nullable=False),
        sa.Column("ingested_at", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("raw_json", sa.Text, nullable=False),
    )
    op.create_index("idx_raw_events_ts", "raw_events", ["ts"])
    op.create_index("idx_raw_events_source", "raw_events", ["source"])
    op.create_index("idx_raw_events_ingested", "raw_events", ["ingested_at"])

    # ------------------------------------------------------------------
    # source_ips — IP intelligence; no FK dependencies
    # ------------------------------------------------------------------
    op.create_table(
        "source_ips",
        sa.Column("ip", sa.Text, primary_key=True),
        sa.Column("first_seen", sa.Text, nullable=False),
        sa.Column("last_seen", sa.Text, nullable=False),
        sa.Column("event_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("country_code", sa.Text, nullable=True),
        sa.Column("country_name", sa.Text, nullable=True),
        sa.Column("asn", sa.Integer, nullable=True),
        sa.Column("asn_org", sa.Text, nullable=True),
        sa.Column("is_tor_exit", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_vpn", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reputation_score", sa.Float, nullable=True),
        sa.Column("tags", sa.Text, nullable=True),
    )
    op.create_index("idx_source_ips_asn", "source_ips", ["asn"])
    op.create_index("idx_source_ips_country", "source_ips", ["country_code"])
    op.create_index("idx_source_ips_last_seen", "source_ips", ["last_seen"])
    op.create_index(
        "idx_source_ips_count",
        "source_ips",
        [sa.text("event_count DESC")],
    )

    # ------------------------------------------------------------------
    # events — primary analytical table; FKs to raw_events and event_types
    # campaign_id FK is omitted here — added via ALTER TABLE in Phase 6.
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("ts", sa.Text, nullable=False),
        sa.Column("src_ip", sa.Text, nullable=True),
        sa.Column("dst_port", sa.Integer, nullable=True),
        sa.Column("protocol", sa.Text, nullable=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("service", sa.Text, nullable=True),
        sa.Column("country_code", sa.Text, nullable=True),
        sa.Column("country_name", sa.Text, nullable=True),
        sa.Column("city", sa.Text, nullable=True),
        sa.Column("asn", sa.Integer, nullable=True),
        sa.Column("asn_org", sa.Text, nullable=True),
        sa.Column("campaign_id", sa.Text, nullable=True),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["id"], ["raw_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_type"], ["event_types.id"]),
    )
    op.create_index("idx_events_ts", "events", ["ts"])
    op.create_index("idx_events_src_ip", "events", ["src_ip"])
    op.create_index("idx_events_type", "events", ["event_type"])
    op.create_index("idx_events_asn", "events", ["asn"])
    op.create_index("idx_events_country", "events", ["country_code"])
    op.create_index("idx_events_campaign", "events", ["campaign_id"])
    op.create_index("idx_events_ts_type", "events", ["ts", "event_type"])
    op.create_index("idx_events_ts_src_ip", "events", ["ts", "src_ip"])

    # ------------------------------------------------------------------
    # audit_log — security event log; no FK dependencies
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("ts", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("auth_method", sa.Text, nullable=True),
        sa.Column("source_ip", sa.Text, nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
    )
    op.create_index("idx_audit_ts", "audit_log", ["ts"])
    op.create_index("idx_audit_event_type", "audit_log", ["event_type"])
    op.create_index("idx_audit_source_ip", "audit_log", ["source_ip"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("events")
    op.drop_table("source_ips")
    op.drop_table("raw_events")
    op.drop_table("event_types")
