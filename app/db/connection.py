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
    Create all Phase 1 tables directly using DDL. Intended for test fixtures
    and local development bootstrapping only.

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
