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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.connection import create_all_tables


def _apply_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


@pytest.fixture
def db_engine():
    """Fresh in-memory SQLite engine per test with Phase 1 schema and seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _apply_pragmas)
    create_all_tables(engine)
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
