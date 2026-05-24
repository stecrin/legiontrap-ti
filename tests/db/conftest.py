"""
DB test fixtures for EventRepository tests.

These fixtures deliberately bypass get_engine() and the module-level singleton
so they have no effect on the existing router/auth test suite. Each test gets
a completely fresh in-memory SQLite database.

Schema bootstrap mirrors 0001_initial_schema.py exactly. When the migration
changes, this file must be updated to match. The two-place duplication is an
accepted trade-off: Alembic cannot run against :memory: (blocked in env.py),
and per-test isolation is more valuable than DRY here.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _apply_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def _bootstrap_schema(engine) -> None:
    """Create all Phase 1 tables and seed event_types. Mirrors 0001_initial_schema.py."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE event_types (
                id               TEXT PRIMARY KEY,
                label            TEXT NOT NULL,
                attack_tactic    TEXT,
                attack_technique TEXT,
                description      TEXT
            )
        """
            )
        )
        conn.execute(
            text(
                """
            INSERT INTO event_types (id, label, attack_tactic, attack_technique) VALUES
            ('auth_failed',    'SSH Authentication Failure', 'Credential Access', 'T1110.001'),
            ('auth_success',   'SSH Authentication Success', 'Initial Access',    'T1078'),
            ('port_scan',      'Port Scan Probe',            'Discovery',         'T1046'),
            ('http_probe',     'HTTP Endpoint Probe',        'Discovery',         'T1595.002'),
            ('malware_upload', 'Malware Upload Attempt',     'Execution',         'T1204'),
            ('command_exec',   'Remote Command Execution',   'Execution',         'T1059'),
            ('unknown',        'Unknown Event Type',          NULL,                NULL)
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE raw_events (
                id          TEXT PRIMARY KEY,
                ts          TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                source      TEXT NOT NULL,
                raw_json    TEXT NOT NULL
            )
        """
            )
        )
        conn.execute(text("CREATE INDEX idx_raw_events_ts ON raw_events(ts)"))
        conn.execute(text("CREATE INDEX idx_raw_events_source ON raw_events(source)"))
        conn.execute(text("CREATE INDEX idx_raw_events_ingested ON raw_events(ingested_at)"))
        conn.execute(
            text(
                """
            CREATE TABLE source_ips (
                ip               TEXT PRIMARY KEY,
                first_seen       TEXT NOT NULL,
                last_seen        TEXT NOT NULL,
                event_count      INTEGER NOT NULL DEFAULT 0,
                country_code     TEXT,
                country_name     TEXT,
                asn              INTEGER,
                asn_org          TEXT,
                is_tor_exit      INTEGER NOT NULL DEFAULT 0,
                is_vpn           INTEGER NOT NULL DEFAULT 0,
                reputation_score REAL,
                tags             TEXT
            )
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE events (
                id             TEXT PRIMARY KEY,
                ts             TEXT NOT NULL,
                src_ip         TEXT,
                dst_port       INTEGER,
                protocol       TEXT,
                event_type     TEXT NOT NULL,
                service        TEXT,
                country_code   TEXT,
                country_name   TEXT,
                city           TEXT,
                asn            INTEGER,
                asn_org        TEXT,
                campaign_id    TEXT,
                schema_version INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (id)         REFERENCES raw_events(id) ON DELETE CASCADE,
                FOREIGN KEY (event_type) REFERENCES event_types(id)
            )
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE TABLE audit_log (
                id          TEXT PRIMARY KEY,
                ts          TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                auth_method TEXT,
                source_ip   TEXT,
                detail      TEXT
            )
        """
            )
        )
        conn.commit()


@pytest.fixture
def db_engine():
    """Fresh in-memory SQLite engine per test with Phase 1 schema and seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _apply_pragmas)
    _bootstrap_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """SQLAlchemy Session bound to the per-test in-memory engine."""
    factory = sessionmaker(db_engine, autocommit=False, autoflush=False)
    session = factory()
    yield session
    session.rollback()
    session.close()
