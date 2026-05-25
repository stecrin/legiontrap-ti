"""
Delete events (and orphaned raw_events) older than a given cutoff.

Usage:
    python scripts/db_prune.py --before 2025-01-01T00:00:00+00:00
    make db-prune PRUNE_BEFORE=2025-01-01T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from app.db.connection import get_engine
from app.db.repository import EventRepository


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Delete LegionTrap events older than a cutoff date."
    )
    parser.add_argument(
        "--before",
        required=True,
        metavar="ISO8601",
        help="Delete events with ts < this timestamp (e.g. 2025-01-01T00:00:00+00:00)",
    )
    args = parser.parse_args(argv)

    try:
        cutoff = datetime.fromisoformat(args.before).astimezone(UTC)
    except ValueError as exc:
        print(f"Error: invalid timestamp: {exc}", file=sys.stderr)
        sys.exit(1)

    engine = get_engine()
    session = sessionmaker(engine)()
    try:
        n = EventRepository(session).delete_events_before(cutoff)
        session.commit()
        print(f"Deleted {n} events before {cutoff.isoformat()}")
    except Exception as exc:
        session.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
