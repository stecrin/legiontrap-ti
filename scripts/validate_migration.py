"""
Validate that the LegionTrap SQLite database was migrated correctly.

Checks:
  - All expected tables are present
  - All expected indexes are present (Alembic migration creates these; create_all_tables does not)
  - Alembic version matches the expected head revision

Exit codes:
  0 — all checks passed (DB is production-ready)
  1 — one or more checks failed

Usage (from project root):
    python scripts/validate_migration.py
    python scripts/validate_migration.py --db-path /path/to/legiontrap.db
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import Engine, create_engine, text

EXPECTED_TABLES: list[str] = [
    "event_types",
    "raw_events",
    "source_ips",
    "events",
    "audit_log",
]

# All indexes created by Alembic migrations up to the current head.
# create_all_tables() does NOT create these — their absence indicates the DB
# was not set up via 'alembic upgrade head'.
EXPECTED_INDEXES: list[str] = [
    # 0001_initial_schema
    "idx_raw_events_ts",
    "idx_raw_events_source",
    "idx_raw_events_ingested",
    "idx_source_ips_asn",
    "idx_source_ips_country",
    "idx_source_ips_last_seen",
    "idx_source_ips_count",
    "idx_events_ts",
    "idx_events_src_ip",
    "idx_events_type",
    "idx_events_asn",
    "idx_events_country",
    "idx_events_campaign",
    "idx_events_ts_type",
    "idx_events_ts_src_ip",
    "idx_audit_ts",
    "idx_audit_event_type",
    "idx_audit_source_ip",
    # 0002_phase2_intelligence_indexes
    "idx_source_ips_reputation",
    "idx_events_src_ip_type",
]

EXPECTED_ALEMBIC_REVISION = "0002"


@dataclass
class ValidationResult:
    missing_tables: list[str] = field(default_factory=list)
    missing_indexes: list[str] = field(default_factory=list)
    alembic_version: str | None = None

    @property
    def valid(self) -> bool:
        return (
            not self.missing_tables
            and not self.missing_indexes
            and self.alembic_version == EXPECTED_ALEMBIC_REVISION
        )


def validate_database(engine: Engine) -> ValidationResult:
    """
    Inspect the database schema and return a ValidationResult.

    Queries sqlite_master for tables and indexes; queries alembic_version
    for the migration revision. Does not modify the database.
    """
    result = ValidationResult()

    with engine.connect() as conn:
        # Check tables
        existing_tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }
        result.missing_tables = [t for t in EXPECTED_TABLES if t not in existing_tables]

        # Check indexes
        existing_indexes = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'index'")
            ).fetchall()
        }
        result.missing_indexes = [i for i in EXPECTED_INDEXES if i not in existing_indexes]

        # Check Alembic version
        if "alembic_version" in existing_tables:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            result.alembic_version = row[0] if row else None

    return result


def print_report(result: ValidationResult, db_path: str) -> None:
    """Print a human-readable validation report to stdout."""
    print(f"\nValidating: {db_path}")

    print("\n[Tables]")
    all_tables = EXPECTED_TABLES[:]
    for t in all_tables:
        mark = "✓" if t not in result.missing_tables else "✗"
        suffix = "  (MISSING)" if t in result.missing_tables else ""
        print(f"  {mark} {t}{suffix}")

    print("\n[Indexes]")
    for idx in EXPECTED_INDEXES:
        mark = "✓" if idx not in result.missing_indexes else "✗"
        suffix = "  (MISSING)" if idx in result.missing_indexes else ""
        print(f"  {mark} {idx}{suffix}")

    print("\n[Alembic]")
    if result.alembic_version:
        rev_ok = result.alembic_version == EXPECTED_ALEMBIC_REVISION
        mark = "✓" if rev_ok else "✗"
        print(f"  {mark} version: {result.alembic_version}")
        if not rev_ok:
            print(f"    expected: {EXPECTED_ALEMBIC_REVISION}")
    else:
        print("  ✗ alembic_version table not present (run 'alembic upgrade head')")

    issues = (
        len(result.missing_tables)
        + len(result.missing_indexes)
        + (0 if result.alembic_version == EXPECTED_ALEMBIC_REVISION else 1)
    )
    print()
    if result.valid:
        print("Result: VALID")
    else:
        print(f"Result: INVALID ({issues} issue(s))")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate LegionTrap SQLite database schema and migration state."
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
            "Error: cannot validate :memory: — set DB_PATH to a file path.",
            file=sys.stderr,
        )
        sys.exit(1)

    engine = create_engine(f"sqlite:///{db_path}")
    result = validate_database(engine)
    engine.dispose()

    print_report(result, db_path)

    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    main()
