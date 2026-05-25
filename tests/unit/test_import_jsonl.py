"""
Unit tests for scripts/import_jsonl.py.

All tests use an isolated file-based SQLite DB (tmp_path) to mirror the
import tool's requirement that DB_PATH must be a real file, not :memory:.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy import event as sa_event

from app.db.connection import create_all_tables
from scripts.import_jsonl import import_files

# ---------------------------------------------------------------------------
# Fixture: per-test file-based SQLite engine with schema bootstrapped
# ---------------------------------------------------------------------------


@pytest.fixture
def import_engine(tmp_path):
    db_path = tmp_path / "import_test.db"
    engine = create_engine(f"sqlite:///{db_path}")

    @sa_event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        dbapi_conn.execute("PRAGMA journal_mode = WAL")

    create_all_tables(engine)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _cowrie_event(
    event_id: str | None = None,
    ts: str = "2025-10-28T18:31:08+00:00",
    source: str = "cowrie",
    event_type: str = "cowrie.login.failed",
    ip: str = "1.2.3.4",
) -> dict:
    return {
        "id": event_id or str(uuid.uuid4()),
        "ts": ts,
        "source": source,
        "type": event_type,
        "data": {"ip": ip, "username": "root", "password": "bad"},
    }


def _row_count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


# ---------------------------------------------------------------------------
# Basic import
# ---------------------------------------------------------------------------


def test_import_single_event(tmp_path, import_engine):
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event()])

    summary = import_files([jsonl], import_engine)

    assert summary.imported == 1
    assert summary.skipped == 0
    assert summary.failed == 0
    assert summary.files_processed == 1
    assert _row_count(import_engine, "raw_events") == 1
    assert _row_count(import_engine, "events") == 1


def test_import_multiple_events(tmp_path, import_engine):
    events = [_cowrie_event() for _ in range(5)]
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, events)

    summary = import_files([jsonl], import_engine)

    assert summary.imported == 5
    assert summary.failed == 0
    assert _row_count(import_engine, "events") == 5


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_import_idempotent_same_file_twice(tmp_path, import_engine):
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event(event_id="fixed-id-001")])

    r1 = import_files([jsonl], import_engine)
    r2 = import_files([jsonl], import_engine)

    assert r1.imported == 1
    assert r2.imported == 0
    assert r2.skipped == 1
    assert _row_count(import_engine, "raw_events") == 1


def test_import_duplicate_id_in_two_files(tmp_path, import_engine):
    eid = str(uuid.uuid4())
    file1 = tmp_path / "f1.jsonl"
    file2 = tmp_path / "f2.jsonl"
    _write_jsonl(file1, [_cowrie_event(event_id=eid)])
    _write_jsonl(file2, [_cowrie_event(event_id=eid)])

    summary = import_files([file1, file2], import_engine)

    assert summary.imported == 1
    assert summary.skipped == 1
    assert _row_count(import_engine, "raw_events") == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_import_malformed_json_counted_as_failed(tmp_path, import_engine):
    jsonl = tmp_path / "events.jsonl"
    jsonl.write_text(
        'not-json\n{"id":"1","ts":"2025-01-01T00:00:00+00:00","source":"x","type":"y"}\n'
    )

    summary = import_files([jsonl], import_engine)

    assert summary.failed == 1
    assert summary.imported == 1


def test_import_missing_required_field_counted_as_failed(tmp_path, import_engine):
    bad = {"id": str(uuid.uuid4()), "source": "cowrie", "type": "auth_failed"}  # missing ts
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [bad])

    summary = import_files([jsonl], import_engine)

    assert summary.failed == 1
    assert summary.imported == 0


def test_import_bad_timestamp_counted_as_failed(tmp_path, import_engine):
    bad = {**_cowrie_event(), "ts": "not-a-timestamp"}
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [bad])

    summary = import_files([jsonl], import_engine)

    assert summary.failed == 1
    assert summary.imported == 0


def test_import_file_not_found_is_skipped(tmp_path, import_engine):
    missing = tmp_path / "does_not_exist.jsonl"
    # A real event in another file to confirm the rest still runs
    good = tmp_path / "good.jsonl"
    _write_jsonl(good, [_cowrie_event()])

    summary = import_files([missing, good], import_engine)

    assert summary.imported == 1
    assert summary.files_processed == 1  # only the found file


# ---------------------------------------------------------------------------
# IP extraction
# ---------------------------------------------------------------------------


def test_import_public_ip_extracted(tmp_path, import_engine):
    eid = str(uuid.uuid4())
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event(event_id=eid, ip="8.8.8.8")])

    import_files([jsonl], import_engine)

    with import_engine.connect() as conn:
        row = conn.execute(text("SELECT src_ip FROM events WHERE id = :id"), {"id": eid}).fetchone()
    assert row[0] == "8.8.8.8"


def test_import_private_ip_stored_as_null(tmp_path, import_engine):
    eid = str(uuid.uuid4())
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event(event_id=eid, ip="192.168.1.1")])

    import_files([jsonl], import_engine)

    with import_engine.connect() as conn:
        row = conn.execute(text("SELECT src_ip FROM events WHERE id = :id"), {"id": eid}).fetchone()
    assert row[0] is None


# ---------------------------------------------------------------------------
# Event type normalization
# ---------------------------------------------------------------------------


def test_import_sensor_native_type_normalized(tmp_path, import_engine):
    """cowrie.login.failed (sensor-native) must be stored as auth_failed."""
    eid = str(uuid.uuid4())
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event(event_id=eid, event_type="cowrie.login.failed")])

    import_files([jsonl], import_engine)

    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT event_type FROM events WHERE id = :id"), {"id": eid}
        ).fetchone()
    assert row[0] == "auth_failed"


def test_import_canonical_type_passes_through(tmp_path, import_engine):
    """auth_failed (already canonical) must not be double-normalized."""
    eid = str(uuid.uuid4())
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event(event_id=eid, event_type="auth_failed")])

    import_files([jsonl], import_engine)

    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT event_type FROM events WHERE id = :id"), {"id": eid}
        ).fetchone()
    assert row[0] == "auth_failed"


def test_import_unknown_type_coerced(tmp_path, import_engine):
    """Unmapped types are coerced to 'unknown' by the repository."""
    eid = str(uuid.uuid4())
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event(event_id=eid, event_type="cowrie.client.version")])

    import_files([jsonl], import_engine)

    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT event_type FROM events WHERE id = :id"), {"id": eid}
        ).fetchone()
    assert row[0] == "unknown"


# ---------------------------------------------------------------------------
# source_ips upsert
# ---------------------------------------------------------------------------


def test_import_public_ip_upserts_source_ips(tmp_path, import_engine):
    jsonl = tmp_path / "events.jsonl"
    _write_jsonl(jsonl, [_cowrie_event(ip="8.8.8.8")])

    import_files([jsonl], import_engine)

    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT event_count FROM source_ips WHERE ip = '8.8.8.8'")
        ).fetchone()
    assert row is not None
    assert row[0] == 1


# ---------------------------------------------------------------------------
# Multiple files
# ---------------------------------------------------------------------------


def test_import_multiple_files(tmp_path, import_engine):
    f1 = tmp_path / "a.jsonl"
    f2 = tmp_path / "b.jsonl"
    _write_jsonl(f1, [_cowrie_event()])
    _write_jsonl(f2, [_cowrie_event(), _cowrie_event()])

    summary = import_files([f1, f2], import_engine)

    assert summary.imported == 3
    assert summary.files_processed == 2
