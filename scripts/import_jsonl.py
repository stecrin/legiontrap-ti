"""
Import JSONL event files into the LegionTrap SQLite database.

Idempotent: events with an already-present ID are silently skipped.
Malformed lines are counted as failed but do not halt the import.

Usage (from project root):
    python scripts/import_jsonl.py storage/events-*.jsonl
    python scripts/import_jsonl.py --db-path /path/to/legiontrap.db events.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy import event as sa_event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.connection import create_all_tables
from app.db.repository import EventRepository
from app.schemas.models import HoneypotEvent, RawEvent
from app.utils.event_utils import extract_src_ip, normalize_event_type, parse_timestamp


@dataclass
class ImportSummary:
    imported: int = 0
    skipped: int = 0  # duplicate event IDs
    failed: int = 0  # parse/validation errors
    files_processed: int = 0


@contextmanager
def _open_session(engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def make_engine(db_path: str) -> Engine:
    """Create a file-based SQLite engine with FK and WAL pragmas enabled."""
    engine = create_engine(f"sqlite:///{db_path}")

    @sa_event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        dbapi_conn.execute("PRAGMA journal_mode = WAL")

    return engine


def import_files(paths: list[Path], engine: Engine) -> ImportSummary:
    """
    Import events from JSONL files into the database via the given engine.

    Each file is processed in a single session/transaction. Per-event SAVEPOINTs
    isolate duplicate-key races from poisoning the batch session. Passing the
    same file(s) twice produces zero new rows on the second run (idempotent).

    Supports both sensor-native type strings ("cowrie.login.failed") and
    already-canonical type strings ("auth_failed") — both pass through
    normalize_event_type correctly.
    """
    summary = ImportSummary()

    for path in paths:
        if not path.exists():
            print(f"  [warn] {path}: not found, skipping", file=sys.stderr)
            continue

        summary.files_processed += 1

        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            print(f"  [error] {path}: cannot read: {exc}", file=sys.stderr)
            summary.failed += 1
            continue

        with _open_session(engine) as session:
            repo = EventRepository(session)

            for lineno, raw_line in enumerate(lines, start=1):
                line = raw_line.strip()
                if not line:
                    continue

                # Stage 1: JSON parse
                try:
                    event_dict: dict[str, Any] = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    summary.failed += 1
                    continue

                # Stage 2: required field validation
                event_id = event_dict.get("id")
                raw_ts = event_dict.get("ts")
                source = event_dict.get("source")
                raw_type = event_dict.get("type")

                if not (event_id and raw_ts and source and raw_type):
                    summary.failed += 1
                    continue

                # Stage 3: timestamp parse (rejection condition)
                ts = parse_timestamp(raw_ts)
                if ts is None:
                    summary.failed += 1
                    continue

                # Stage 4: deduplication
                if repo.event_exists(event_id):
                    summary.skipped += 1
                    continue

                # Stage 5: normalization
                event_type = normalize_event_type(raw_type, source)

                raw_data = event_dict.get("data")
                data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

                src_ip = extract_src_ip(event_dict)

                # Stage 6: persistence — atomic per-event via SAVEPOINT
                sp = session.begin_nested()
                try:
                    raw_event = RawEvent(
                        id=event_id,
                        ts=str(raw_ts),
                        source=source,
                        type=raw_type,
                        data=data,
                    )
                    repo.insert_raw_event(raw_event)
                    honeypot = HoneypotEvent(
                        id=event_id,
                        ts=ts,
                        ingested_at=datetime.now(UTC),
                        source=source,
                        event_type=event_type,
                        src_ip=src_ip,
                    )
                    repo.insert_event(honeypot)
                    if src_ip:
                        repo.upsert_source_ip(src_ip, ts)
                    sp.commit()
                    summary.imported += 1
                except IntegrityError:
                    sp.rollback()
                    summary.skipped += 1
                except Exception as exc:
                    sp.rollback()
                    summary.failed += 1
                    print(
                        f"  [error] {path}:{lineno} id={event_id}: {exc}",
                        file=sys.stderr,
                    )

    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Import JSONL event files into the LegionTrap SQLite database."
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        metavar="FILE",
        help="JSONL file(s) to import",
    )
    parser.add_argument(
        "--db-path",
        metavar="PATH",
        help="SQLite DB path (overrides DB_PATH env var / settings)",
    )
    args = parser.parse_args(argv)

    if args.db_path:
        db_path = args.db_path
    else:
        from app.core.config import settings

        db_path = settings.DB_PATH

    if db_path == ":memory:":
        print(
            "Error: cannot import to :memory: — set DB_PATH to a file path.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Target DB : {db_path}")
    engine = make_engine(db_path)
    create_all_tables(engine)

    print(f"Files     : {len(args.files)}")
    summary = import_files(args.files, engine)
    engine.dispose()

    print()
    print(f"imported  : {summary.imported}")
    print(f"skipped   : {summary.skipped}  (duplicate IDs)")
    print(f"failed    : {summary.failed}  (parse/validation errors)")


if __name__ == "__main__":
    main()
