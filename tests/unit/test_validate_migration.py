"""
Unit tests for scripts/validate_migration.py.

Two scenarios are tested:
  1. DB bootstrapped with create_all_tables() — no indexes, no alembic_version → INVALID
  2. DB with full schema (tables + all indexes + alembic_version) → VALID

The 'full schema' case is constructed without running Alembic directly so these
tests remain fast and self-contained. Run 'make db-validate' against a real
Alembic-migrated DB to exercise the live migration path.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.db.connection import create_all_tables
from scripts.validate_migration import (
    EXPECTED_ALEMBIC_REVISION,
    EXPECTED_INDEXES,
    validate_database,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bootstrap_engine(tmp_path, suffix="test.db"):
    engine = create_engine(f"sqlite:///{tmp_path / suffix}")
    create_all_tables(engine)
    return engine


def _add_full_indexes_and_revision(engine) -> None:
    """
    Add all expected indexes and the alembic_version table+row.
    Simulates 'alembic upgrade head' without running the Alembic CLI.
    """
    with engine.connect() as conn:
        # raw_events indexes
        conn.execute(text("CREATE INDEX idx_raw_events_ts ON raw_events(ts)"))
        conn.execute(text("CREATE INDEX idx_raw_events_source ON raw_events(source)"))
        conn.execute(text("CREATE INDEX idx_raw_events_ingested ON raw_events(ingested_at)"))

        # source_ips indexes
        conn.execute(text("CREATE INDEX idx_source_ips_asn ON source_ips(asn)"))
        conn.execute(text("CREATE INDEX idx_source_ips_country ON source_ips(country_code)"))
        conn.execute(text("CREATE INDEX idx_source_ips_last_seen ON source_ips(last_seen)"))
        conn.execute(text("CREATE INDEX idx_source_ips_count ON source_ips(event_count DESC)"))

        # events indexes
        conn.execute(text("CREATE INDEX idx_events_ts ON events(ts)"))
        conn.execute(text("CREATE INDEX idx_events_src_ip ON events(src_ip)"))
        conn.execute(text("CREATE INDEX idx_events_type ON events(event_type)"))
        conn.execute(text("CREATE INDEX idx_events_asn ON events(asn)"))
        conn.execute(text("CREATE INDEX idx_events_country ON events(country_code)"))
        conn.execute(text("CREATE INDEX idx_events_campaign ON events(campaign_id)"))
        conn.execute(text("CREATE INDEX idx_events_ts_type ON events(ts, event_type)"))
        conn.execute(text("CREATE INDEX idx_events_ts_src_ip ON events(ts, src_ip)"))

        # audit_log indexes
        conn.execute(text("CREATE INDEX idx_audit_ts ON audit_log(ts)"))
        conn.execute(text("CREATE INDEX idx_audit_event_type ON audit_log(event_type)"))
        conn.execute(text("CREATE INDEX idx_audit_source_ip ON audit_log(source_ip)"))

        # Alembic version table (mirrors what Alembic creates)
        conn.execute(
            text(
                "CREATE TABLE alembic_version ("
                "version_num VARCHAR(32) NOT NULL "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY)"
            )
        )
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": EXPECTED_ALEMBIC_REVISION},
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Invalid: create_all_tables DB (no indexes, no alembic_version)
# ---------------------------------------------------------------------------


def test_validate_create_all_tables_db_is_invalid(tmp_path):
    engine = _bootstrap_engine(tmp_path)
    result = validate_database(engine)
    engine.dispose()

    assert not result.valid


def test_validate_create_all_tables_reports_missing_indexes(tmp_path):
    engine = _bootstrap_engine(tmp_path)
    result = validate_database(engine)
    engine.dispose()

    assert len(result.missing_indexes) == len(EXPECTED_INDEXES)
    for idx in EXPECTED_INDEXES:
        assert idx in result.missing_indexes


def test_validate_create_all_tables_has_all_tables(tmp_path):
    """create_all_tables creates all 5 expected tables — only indexes are missing."""
    engine = _bootstrap_engine(tmp_path)
    result = validate_database(engine)
    engine.dispose()

    assert result.missing_tables == []


def test_validate_create_all_tables_has_no_alembic_version(tmp_path):
    engine = _bootstrap_engine(tmp_path)
    result = validate_database(engine)
    engine.dispose()

    assert result.alembic_version is None


# ---------------------------------------------------------------------------
# Valid: full schema (tables + indexes + alembic_version)
# ---------------------------------------------------------------------------


def test_validate_full_schema_is_valid(tmp_path):
    engine = _bootstrap_engine(tmp_path, "full.db")
    _add_full_indexes_and_revision(engine)
    result = validate_database(engine)
    engine.dispose()

    assert result.valid


def test_validate_full_schema_has_no_missing_tables(tmp_path):
    engine = _bootstrap_engine(tmp_path, "full.db")
    _add_full_indexes_and_revision(engine)
    result = validate_database(engine)
    engine.dispose()

    assert result.missing_tables == []


def test_validate_full_schema_has_no_missing_indexes(tmp_path):
    engine = _bootstrap_engine(tmp_path, "full.db")
    _add_full_indexes_and_revision(engine)
    result = validate_database(engine)
    engine.dispose()

    assert result.missing_indexes == []


def test_validate_full_schema_reports_correct_revision(tmp_path):
    engine = _bootstrap_engine(tmp_path, "full.db")
    _add_full_indexes_and_revision(engine)
    result = validate_database(engine)
    engine.dispose()

    assert result.alembic_version == EXPECTED_ALEMBIC_REVISION


# ---------------------------------------------------------------------------
# Partial invalid: all tables + all indexes but no alembic_version
# ---------------------------------------------------------------------------


def test_validate_missing_alembic_version_is_invalid(tmp_path):
    engine = _bootstrap_engine(tmp_path, "partial.db")
    with engine.connect() as conn:
        # Add all indexes but skip alembic_version
        conn.execute(text("CREATE INDEX idx_raw_events_ts ON raw_events(ts)"))
        conn.execute(text("CREATE INDEX idx_raw_events_source ON raw_events(source)"))
        conn.execute(text("CREATE INDEX idx_raw_events_ingested ON raw_events(ingested_at)"))
        conn.execute(text("CREATE INDEX idx_source_ips_asn ON source_ips(asn)"))
        conn.execute(text("CREATE INDEX idx_source_ips_country ON source_ips(country_code)"))
        conn.execute(text("CREATE INDEX idx_source_ips_last_seen ON source_ips(last_seen)"))
        conn.execute(text("CREATE INDEX idx_source_ips_count ON source_ips(event_count DESC)"))
        conn.execute(text("CREATE INDEX idx_events_ts ON events(ts)"))
        conn.execute(text("CREATE INDEX idx_events_src_ip ON events(src_ip)"))
        conn.execute(text("CREATE INDEX idx_events_type ON events(event_type)"))
        conn.execute(text("CREATE INDEX idx_events_asn ON events(asn)"))
        conn.execute(text("CREATE INDEX idx_events_country ON events(country_code)"))
        conn.execute(text("CREATE INDEX idx_events_campaign ON events(campaign_id)"))
        conn.execute(text("CREATE INDEX idx_events_ts_type ON events(ts, event_type)"))
        conn.execute(text("CREATE INDEX idx_events_ts_src_ip ON events(ts, src_ip)"))
        conn.execute(text("CREATE INDEX idx_audit_ts ON audit_log(ts)"))
        conn.execute(text("CREATE INDEX idx_audit_event_type ON audit_log(event_type)"))
        conn.execute(text("CREATE INDEX idx_audit_source_ip ON audit_log(source_ip)"))
        conn.commit()

    result = validate_database(engine)
    engine.dispose()

    assert not result.valid
    assert result.missing_indexes == []
    assert result.alembic_version is None


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------


def test_main_exits_1_on_invalid_db(tmp_path):
    db_file = str(tmp_path / "invalid.db")
    engine = create_engine(f"sqlite:///{db_file}")
    create_all_tables(engine)
    engine.dispose()

    from scripts.validate_migration import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--db-path", db_file])
    assert exc_info.value.code == 1


def test_main_exits_0_on_valid_db(tmp_path):
    db_file = str(tmp_path / "valid.db")
    engine = create_engine(f"sqlite:///{db_file}")
    create_all_tables(engine)
    _add_full_indexes_and_revision(engine)
    engine.dispose()

    from scripts.validate_migration import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--db-path", db_file])
    assert exc_info.value.code == 0
