"""
SQLite connection factory for LegionTrap TI.

Sync-only SQLAlchemy 2.x engine. SQLite has no true async I/O; aiosqlite is a
thread-pool wrapper with no benefit over sync + FastAPI's thread pool executor.
All database access goes through app/db/repository.py — no SQL in routers.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_engine: Engine | None = None


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
        connect_args = {}
        if settings.DB_PATH == ":memory:":
            # Allow the same in-memory DB to be shared across connections in tests.
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            f"sqlite:///{settings.DB_PATH}",
            connect_args={"check_same_thread": False},
        )
        event.listen(_engine, "connect", _apply_pragmas)

    return _engine


def reset_engine() -> None:
    """Dispose the current engine and clear the singleton. Used in tests only."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


_SessionLocal: sessionmaker | None = None


def _get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


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
