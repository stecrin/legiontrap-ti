"""
SQLite connection factory for LegionTrap TI.

Sync-only SQLAlchemy 2.x engine. SQLite has no true async I/O; aiosqlite is a
thread-pool wrapper with no benefit over sync + FastAPI's thread pool executor.
All database access goes through app/db/repository.py — no SQL in routers.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _apply_pragmas(dbapi_conn, _connection_record) -> None:
    """Apply SQLite PRAGMAs on every new connection per DATABASE_SCHEMA.md."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def get_engine() -> Engine:
    """Return the module-level singleton Engine, creating it on first call."""
    global _engine
    if _engine is None:
        if settings.DB_PATH == ":memory:":
            # StaticPool forces all connections to share the same in-memory DB.
            # Without it, each new connection gets an empty database.
            _engine = create_engine(
                "sqlite:///:memory:",
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            _engine = create_engine(
                f"sqlite:///{settings.DB_PATH}",
                connect_args={"check_same_thread": False},
            )
        event.listen(_engine, "connect", _apply_pragmas)
    return _engine


def reset_engine() -> None:
    """Dispose the current engine and clear both singletons. Used in tests only."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
    _SessionLocal = None


def _get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


def create_all_tables(engine: Engine) -> None:
    """
    Create all tables directly using DDL. Intended for test fixtures and local
    development bootstrapping only.

    Production deployments must use `alembic upgrade head` instead. This
    function must never be called from application startup code.

    Note: does NOT create indexes. Run `alembic upgrade head` to add indexes
    and register the Alembic revision; use `make db-validate` to check state.
    """
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS event_types ("
                "id TEXT PRIMARY KEY, label TEXT NOT NULL, "
                "attack_tactic TEXT, attack_technique TEXT, description TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT OR IGNORE INTO event_types "
                "(id, label, attack_tactic, attack_technique) VALUES "
                "('auth_failed','SSH Authentication Failure','Credential Access','T1110.001'),"
                "('auth_success','SSH Authentication Success','Initial Access','T1078'),"
                "('port_scan','Port Scan Probe','Discovery','T1046'),"
                "('http_probe','HTTP Endpoint Probe','Discovery','T1595.002'),"
                "('malware_upload','Malware Upload Attempt','Execution','T1204'),"
                "('command_exec','Remote Command Execution','Execution','T1059'),"
                "('unknown','Unknown Event Type',NULL,NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS raw_events ("
                "id TEXT PRIMARY KEY, ts TEXT NOT NULL, ingested_at TEXT NOT NULL, "
                "source TEXT NOT NULL, raw_json TEXT NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS source_ips ("
                "ip TEXT PRIMARY KEY, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, "
                "event_count INTEGER NOT NULL DEFAULT 0, country_code TEXT, "
                "country_name TEXT, asn INTEGER, asn_org TEXT, "
                "is_tor_exit INTEGER NOT NULL DEFAULT 0, "
                "is_vpn INTEGER NOT NULL DEFAULT 0, "
                "reputation_score REAL, tags TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS events ("
                "id TEXT PRIMARY KEY, ts TEXT NOT NULL, src_ip TEXT, "
                "dst_port INTEGER, protocol TEXT, event_type TEXT NOT NULL, "
                "service TEXT, country_code TEXT, country_name TEXT, city TEXT, "
                "asn INTEGER, asn_org TEXT, campaign_id TEXT, "
                "schema_version INTEGER NOT NULL DEFAULT 1, "
                "FOREIGN KEY (id) REFERENCES raw_events(id) ON DELETE CASCADE, "
                "FOREIGN KEY (event_type) REFERENCES event_types(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS audit_log ("
                "id TEXT PRIMARY KEY, ts TEXT NOT NULL, event_type TEXT NOT NULL, "
                "auth_method TEXT, source_ip TEXT, detail TEXT)"
            )
        )

        # Phase 4 — behavioral memory and campaign intelligence tables.
        # Created in FK dependency order: behavioral_fingerprints and campaigns
        # have no cross-dependency; campaign_members / observations / tags depend
        # on campaigns (and behavioral_fingerprints depends on source_ips).
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS behavioral_fingerprints ("
                "id TEXT PRIMARY KEY, "
                "source_ip TEXT NOT NULL UNIQUE, "
                "fingerprint_version INTEGER NOT NULL DEFAULT 1, "
                "computed_at TEXT NOT NULL, "
                "event_count_at_computation INTEGER NOT NULL, "
                "timing_features TEXT, "
                "sequence_features TEXT, "
                "protocol_features TEXT, "
                "credential_features TEXT, "
                "target_features TEXT, "
                "tool_signals TEXT, "
                "confidence REAL NOT NULL DEFAULT 0.5, "
                "FOREIGN KEY (source_ip) REFERENCES source_ips(ip))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS campaigns ("
                "id TEXT PRIMARY KEY, "
                "name TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'active', "
                "confidence REAL NOT NULL DEFAULT 0.5, "
                "first_seen TEXT NOT NULL, "
                "last_seen TEXT NOT NULL, "
                "dormant_since TEXT, "
                "reactivation_count INTEGER NOT NULL DEFAULT 0, "
                "member_ip_count INTEGER NOT NULL DEFAULT 0, "
                "attack_tactic_dist TEXT, "
                "top_target_ports TEXT, "
                "notes TEXT, "
                "created_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL, "
                "representative_fingerprint_json TEXT, "
                "behavioral_stability_json TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS campaign_members ("
                "campaign_id TEXT NOT NULL, "
                "source_ip TEXT NOT NULL, "
                "confidence REAL NOT NULL DEFAULT 0.5, "
                "added_at TEXT NOT NULL, "
                "last_active TEXT NOT NULL, "
                "PRIMARY KEY (campaign_id, source_ip), "
                "FOREIGN KEY (campaign_id) REFERENCES campaigns(id), "
                "FOREIGN KEY (source_ip) REFERENCES source_ips(ip))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS campaign_observations ("
                "id TEXT PRIMARY KEY, "
                "campaign_id TEXT NOT NULL, "
                "source_ip TEXT NOT NULL, "
                "observed_at TEXT NOT NULL, "
                "event_count INTEGER NOT NULL, "
                "is_reactivation INTEGER NOT NULL DEFAULT 0, "
                "dormancy_gap_days REAL, "
                "notes TEXT, "
                "analyst_review_json TEXT, "
                "FOREIGN KEY (campaign_id) REFERENCES campaigns(id))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS campaign_tags ("
                "campaign_id TEXT NOT NULL, "
                "tag TEXT NOT NULL, "
                "source TEXT NOT NULL DEFAULT 'auto', "
                "created_at TEXT NOT NULL, "
                "PRIMARY KEY (campaign_id, tag), "
                "FOREIGN KEY (campaign_id) REFERENCES campaigns(id))"
            )
        )

        # Phase 6 — async job infrastructure.
        # processing_jobs is the central coordination table for all async
        # operations: AI summary/brief execution, clustering deduplication,
        # and future long-running intelligence tasks.
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS processing_jobs ("
                "id TEXT PRIMARY KEY, "
                "job_type TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'pending', "
                "created_at TEXT NOT NULL, "
                "started_at TEXT, "
                "completed_at TEXT, "
                "failed_at TEXT, "
                "triggered_by TEXT, "
                "resource_type TEXT, "
                "resource_id TEXT, "
                "deduplication_key TEXT, "
                "progress_percent INTEGER NOT NULL DEFAULT 0, "
                "result_summary_json TEXT, "
                "error_message TEXT, "
                "backend_metadata_json TEXT, "
                "ai_output_id TEXT)"
            )
        )

        # Phase 6 PR A2 — immutable AI output records.
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS ai_outputs ("
                "id TEXT PRIMARY KEY, "
                "job_id TEXT NOT NULL, "
                "output_type TEXT NOT NULL, "
                "resource_type TEXT, "
                "resource_id TEXT, "
                "content TEXT, "
                "backend TEXT NOT NULL, "
                "model_name TEXT NOT NULL, "
                "prompt_hash TEXT NOT NULL, "
                "payload_bytes INTEGER NOT NULL, "
                "source_records_json TEXT NOT NULL, "
                "safety_flags_json TEXT, "
                "rejected INTEGER NOT NULL DEFAULT 0, "
                "rejection_reason TEXT, "
                "truncated INTEGER NOT NULL DEFAULT 0, "
                "data_quality_score REAL, "
                "generated_at TEXT NOT NULL, "
                "triggered_by TEXT)"
            )
        )

        # Phase 6 PR A3 — AI call audit log (metadata only, no content).
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS ai_audit_log ("
                "id TEXT PRIMARY KEY, "
                "job_id TEXT, "
                "output_id TEXT, "
                "triggered_by TEXT, "
                "backend TEXT NOT NULL, "
                "model_name TEXT NOT NULL, "
                "operation_type TEXT NOT NULL, "
                "resource_type TEXT, "
                "resource_id TEXT, "
                "payload_bytes INTEGER NOT NULL DEFAULT 0, "
                "response_bytes INTEGER NOT NULL DEFAULT 0, "
                "latency_ms INTEGER NOT NULL DEFAULT 0, "
                "status TEXT NOT NULL, "
                "error_type TEXT, "
                "created_at TEXT NOT NULL)"
            )
        )

        # Phase 6 Group B — fingerprint history (append-only longitudinal snapshots).
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS fingerprint_history ("
                "id TEXT PRIMARY KEY, "
                "fingerprint_id TEXT, "
                "source_ip TEXT NOT NULL, "
                "campaign_id TEXT, "
                "fingerprint_version INTEGER NOT NULL, "
                "computed_at TEXT NOT NULL, "
                "event_count_at_computation INTEGER NOT NULL, "
                "confidence REAL NOT NULL, "
                "timing_features TEXT, "
                "sequence_features TEXT, "
                "protocol_features TEXT, "
                "credential_features TEXT, "
                "target_features TEXT, "
                "created_at TEXT NOT NULL)"
            )
        )

        # Phase 6 Group D — actor identity schema foundations for Phase 7.
        # actor_profiles and campaign_lineage are empty containers.  No row is
        # created automatically by clustering, lifecycle, or AI code paths.
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS actor_profiles ("
                "id TEXT PRIMARY KEY, "
                "display_name TEXT NOT NULL, "
                "confidence REAL NOT NULL DEFAULT 0.5, "
                "status TEXT NOT NULL DEFAULT 'active', "
                "representative_fingerprint_json TEXT, "
                "behavioral_stability_json TEXT, "
                "notes TEXT, "
                "created_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS campaign_lineage ("
                "id TEXT PRIMARY KEY, "
                "actor_profile_id TEXT NOT NULL, "
                "campaign_id TEXT NOT NULL, "
                "relationship_type TEXT NOT NULL, "
                "confidence REAL NOT NULL DEFAULT 0.5, "
                "evidence_json TEXT, "
                "created_at TEXT NOT NULL, "
                "FOREIGN KEY (actor_profile_id) REFERENCES actor_profiles(id), "
                "FOREIGN KEY (campaign_id) REFERENCES campaigns(id))"
            )
        )

        # Phase 7 Group A — per-campaign similarity weight profiles.
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS campaign_weight_profiles ("
                "campaign_id TEXT PRIMARY KEY, "
                "weight_timing REAL NOT NULL, "
                "weight_sequence REAL NOT NULL, "
                "weight_protocol REAL NOT NULL, "
                "weight_credential REAL NOT NULL, "
                "weight_target REAL NOT NULL, "
                "review_count INTEGER NOT NULL DEFAULT 0, "
                "confirmed_count INTEGER NOT NULL DEFAULT 0, "
                "denied_count INTEGER NOT NULL DEFAULT 0, "
                "adjustment_log_json TEXT NOT NULL DEFAULT '[]', "
                "computed_at TEXT NOT NULL, "
                "updated_at TEXT NOT NULL, "
                "FOREIGN KEY (campaign_id) REFERENCES campaigns(id))"
            )
        )

        # Phase 7 Group A — behavioral drift alerts.
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS behavioral_alerts ("
                "id TEXT PRIMARY KEY, "
                "campaign_id TEXT NOT NULL, "
                "alert_type TEXT NOT NULL, "
                "dimension TEXT, "
                "threshold_configured REAL NOT NULL, "
                "observed_value REAL NOT NULL, "
                "stability_snapshot_json TEXT NOT NULL, "
                "triggered_at TEXT NOT NULL, "
                "acknowledged_at TEXT, "
                "acknowledged_notes TEXT, "
                "FOREIGN KEY (campaign_id) REFERENCES campaigns(id))"
            )
        )

        conn.commit()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager that yields a SQLAlchemy Session and commits on clean exit,
    rolls back on exception, and always closes the session.

    Usage:
        with get_session() as session:
            session.execute(text("SELECT 1"))
    """
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
