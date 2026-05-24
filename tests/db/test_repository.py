"""
Unit tests for EventRepository.

All tests use an isolated in-memory SQLite DB (from db_session fixture).
No app startup, no HTTP, no routers. Pure repository layer validation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.repository import EventRepository
from app.schemas.models import EnrichedEvent, HoneypotEvent, RawEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTC = UTC


def _raw(
    event_id: str | None = None,
    ts: str = "2025-10-28T18:31:08+00:00",
    source: str = "cowrie",
    event_type: str = "auth_failed",
    ip: str = "203.0.113.2",
) -> RawEvent:
    return RawEvent(
        id=event_id or str(uuid.uuid4()),
        ts=ts,
        source=source,
        type=event_type,
        data={"ip": ip, "username": "root", "password": "bad"},
    )


def _honeypot(
    event_id: str,
    ts: datetime | None = None,
    src_ip: str | None = "203.0.113.2",
    event_type: str = "auth_failed",
) -> HoneypotEvent:
    return HoneypotEvent(
        id=event_id,
        ts=ts or datetime(2025, 10, 28, 18, 31, 8, tzinfo=UTC),
        ingested_at=datetime.now(UTC),
        source="cowrie",
        event_type=event_type,
        src_ip=src_ip,
        protocol="tcp",
        service="ssh",
    )


def _enriched(event_id: str, ts: datetime | None = None) -> EnrichedEvent:
    return EnrichedEvent(
        id=event_id,
        ts=ts or datetime(2025, 10, 28, 18, 31, 8, tzinfo=UTC),
        ingested_at=datetime.now(UTC),
        source="cowrie",
        event_type="auth_failed",
        src_ip="203.0.113.2",
        protocol="tcp",
        service="ssh",
        country_code="US",
        country_name="United States",
        city="Ashburn",
        asn=15169,
        asn_org="Google LLC",
    )


# ---------------------------------------------------------------------------
# insert_raw_event
# ---------------------------------------------------------------------------


def test_insert_raw_event_writes_row(db_session):
    repo = EventRepository(db_session)
    raw = _raw()
    repo.insert_raw_event(raw)
    db_session.flush()

    row = db_session.execute(
        text("SELECT id, source FROM raw_events WHERE id = :id"),
        {"id": raw.id},
    ).fetchone()
    assert row is not None
    assert row[0] == raw.id
    assert row[1] == "cowrie"


def test_insert_raw_event_stores_full_json(db_session):
    repo = EventRepository(db_session)
    raw = _raw()
    repo.insert_raw_event(raw)
    db_session.flush()

    row = db_session.execute(
        text("SELECT raw_json FROM raw_events WHERE id = :id"),
        {"id": raw.id},
    ).fetchone()
    assert row is not None
    import json

    parsed = json.loads(row[0])
    assert parsed["id"] == raw.id
    assert parsed["source"] == "cowrie"


def test_insert_raw_event_duplicate_raises_integrity_error(db_session):
    repo = EventRepository(db_session)
    raw = _raw()
    repo.insert_raw_event(raw)
    db_session.flush()

    with pytest.raises(IntegrityError):
        repo.insert_raw_event(raw)
        db_session.flush()


# ---------------------------------------------------------------------------
# insert_event
# ---------------------------------------------------------------------------


def test_insert_event_writes_row(db_session):
    repo = EventRepository(db_session)
    raw = _raw(event_id := str(uuid.uuid4()))
    repo.insert_raw_event(raw)
    event = _honeypot(event_id)
    repo.insert_event(event)
    db_session.flush()

    row = db_session.execute(
        text("SELECT id, src_ip, event_type FROM events WHERE id = :id"),
        {"id": event_id},
    ).fetchone()
    assert row is not None
    assert row[1] == "203.0.113.2"
    assert row[2] == "auth_failed"


def test_insert_event_does_not_leak_ingested_at_or_source(db_session):
    """ingested_at and source must not appear in the events table INSERT."""
    repo = EventRepository(db_session)
    eid = str(uuid.uuid4())
    repo.insert_raw_event(_raw(eid))
    # If ingested_at or source were included in the INSERT, SQLite would raise
    # OperationalError: table events has no column named ingested_at.
    repo.insert_event(_honeypot(eid))
    db_session.flush()

    cols = db_session.execute(text("PRAGMA table_info(events)")).fetchall()
    col_names = {row[1] for row in cols}
    assert "ingested_at" not in col_names
    assert "source" not in col_names


def test_insert_enriched_event_stores_geoip_fields(db_session):
    repo = EventRepository(db_session)
    eid = str(uuid.uuid4())
    repo.insert_raw_event(_raw(eid))
    repo.insert_event(_enriched(eid))
    db_session.flush()

    row = db_session.execute(
        text("SELECT country_code, country_name, city, asn, asn_org " "FROM events WHERE id = :id"),
        {"id": eid},
    ).fetchone()
    assert row[0] == "US"
    assert row[1] == "United States"
    assert row[2] == "Ashburn"
    assert row[3] == 15169
    assert row[4] == "Google LLC"


def test_insert_honeypot_event_has_null_geoip_fields(db_session):
    """HoneypotEvent (no GeoIP) must produce NULL GeoIP columns, not an error."""
    repo = EventRepository(db_session)
    eid = str(uuid.uuid4())
    repo.insert_raw_event(_raw(eid))
    repo.insert_event(_honeypot(eid))
    db_session.flush()

    row = db_session.execute(
        text("SELECT country_code, asn FROM events WHERE id = :id"),
        {"id": eid},
    ).fetchone()
    assert row[0] is None
    assert row[1] is None


def test_insert_event_unknown_type_coerced_to_unknown(db_session):
    """event_type not in event_types must be stored as 'unknown', not raise FK error."""
    repo = EventRepository(db_session)
    eid = str(uuid.uuid4())
    repo.insert_raw_event(_raw(eid))
    repo.insert_event(_honeypot(eid, event_type="cowrie_client_version"))
    db_session.flush()

    row = db_session.execute(
        text("SELECT event_type FROM events WHERE id = :id"),
        {"id": eid},
    ).fetchone()
    assert row[0] == "unknown"


def test_insert_event_without_raw_event_raises_fk_error(db_session):
    """events.id is a FK to raw_events.id — inserting without the parent must fail."""
    repo = EventRepository(db_session)
    eid = str(uuid.uuid4())
    # No insert_raw_event call — SQLite enforces FK immediately with PRAGMA ON.
    with pytest.raises(IntegrityError):
        repo.insert_event(_honeypot(eid))
        db_session.flush()


# ---------------------------------------------------------------------------
# event_exists
# ---------------------------------------------------------------------------


def test_event_exists_true_after_insert(db_session):
    repo = EventRepository(db_session)
    raw = _raw()
    repo.insert_raw_event(raw)
    db_session.flush()
    assert repo.event_exists(raw.id) is True


def test_event_exists_false_for_unknown_id(db_session):
    repo = EventRepository(db_session)
    assert repo.event_exists(str(uuid.uuid4())) is False


# ---------------------------------------------------------------------------
# upsert_source_ip
# ---------------------------------------------------------------------------


def test_upsert_source_ip_creates_row(db_session):
    repo = EventRepository(db_session)
    repo.upsert_source_ip("1.2.3.4", datetime(2025, 1, 1, tzinfo=UTC))
    db_session.flush()

    row = db_session.execute(
        text("SELECT ip, event_count FROM source_ips WHERE ip = '1.2.3.4'")
    ).fetchone()
    assert row is not None
    assert row[0] == "1.2.3.4"
    assert row[1] == 1


def test_upsert_source_ip_increments_event_count(db_session):
    repo = EventRepository(db_session)
    ts1 = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    ts2 = datetime(2025, 1, 1, 1, 0, tzinfo=UTC)
    repo.upsert_source_ip("1.2.3.4", ts1)
    db_session.flush()
    repo.upsert_source_ip("1.2.3.4", ts2)
    db_session.flush()

    row = db_session.execute(
        text("SELECT event_count FROM source_ips WHERE ip = '1.2.3.4'")
    ).fetchone()
    assert row[0] == 2


def test_upsert_source_ip_preserves_first_seen(db_session):
    repo = EventRepository(db_session)
    ts1 = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    ts2 = datetime(2025, 6, 1, 0, 0, tzinfo=UTC)
    repo.upsert_source_ip("1.2.3.4", ts1)
    db_session.flush()
    repo.upsert_source_ip("1.2.3.4", ts2)
    db_session.flush()

    row = db_session.execute(
        text("SELECT first_seen, last_seen FROM source_ips WHERE ip = '1.2.3.4'")
    ).fetchone()
    assert row[0] == ts1.isoformat()
    assert row[1] == ts2.isoformat()


def test_upsert_source_ip_stores_geoip_fields(db_session):
    repo = EventRepository(db_session)
    repo.upsert_source_ip(
        "1.2.3.4",
        datetime(2025, 1, 1, tzinfo=UTC),
        country_code="DE",
        country_name="Germany",
        asn=3320,
        asn_org="Deutsche Telekom",
    )
    db_session.flush()

    row = db_session.execute(
        text(
            "SELECT country_code, country_name, asn, asn_org "
            "FROM source_ips WHERE ip = '1.2.3.4'"
        )
    ).fetchone()
    assert row[0] == "DE"
    assert row[1] == "Germany"
    assert row[2] == 3320
    assert row[3] == "Deutsche Telekom"


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


def _insert_full_event(repo, eid, ts, src_ip="1.1.1.1"):
    """Helper: insert raw + event row pair for stats/listing tests."""
    repo.insert_raw_event(RawEvent(id=eid, ts=ts.isoformat(), source="cowrie", type="auth_failed"))
    repo.insert_event(
        HoneypotEvent(
            id=eid,
            ts=ts,
            ingested_at=datetime.now(UTC),
            source="cowrie",
            event_type="auth_failed",
            src_ip=src_ip,
        )
    )


def test_get_stats_empty_db(db_session):
    repo = EventRepository(db_session)
    stats = repo.get_stats()
    assert stats["total_events"] == 0
    assert stats["unique_ips"] == 0
    assert stats["last_24h"] == 0


def test_get_stats_counts_inserted_events(db_session):
    repo = EventRepository(db_session)
    now = datetime.now(UTC)
    _insert_full_event(repo, str(uuid.uuid4()), now, "1.1.1.1")
    _insert_full_event(repo, str(uuid.uuid4()), now, "2.2.2.2")
    _insert_full_event(repo, str(uuid.uuid4()), now, "1.1.1.1")  # duplicate IP
    db_session.flush()

    stats = repo.get_stats()
    assert stats["total_events"] == 3
    assert stats["unique_ips"] == 2


def test_get_stats_last_24h_excludes_old_events(db_session):
    repo = EventRepository(db_session)
    now = datetime.now(UTC)
    old = now - timedelta(hours=25)
    _insert_full_event(repo, str(uuid.uuid4()), now, "1.1.1.1")
    _insert_full_event(repo, str(uuid.uuid4()), old, "2.2.2.2")
    db_session.flush()

    stats = repo.get_stats()
    assert stats["total_events"] == 2
    assert stats["last_24h"] == 1


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


def test_list_events_returns_newest_first(db_session):
    repo = EventRepository(db_session)
    t1 = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
    t3 = datetime(2025, 1, 3, 0, 0, tzinfo=UTC)
    id1, id2, id3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    _insert_full_event(repo, id1, t1)
    _insert_full_event(repo, id2, t2)
    _insert_full_event(repo, id3, t3)
    db_session.flush()

    events = repo.list_events(limit=10)
    ids = [e["id"] for e in events]
    assert ids == [id3, id2, id1]


def test_list_events_respects_limit(db_session):
    repo = EventRepository(db_session)
    now = datetime.now(UTC)
    for _ in range(5):
        _insert_full_event(repo, str(uuid.uuid4()), now)
    db_session.flush()

    assert len(repo.list_events(limit=3)) == 3


def test_list_events_empty_db(db_session):
    repo = EventRepository(db_session)
    assert repo.list_events() == []


def test_list_events_returns_dict_with_expected_keys(db_session):
    repo = EventRepository(db_session)
    eid = str(uuid.uuid4())
    _insert_full_event(repo, eid, datetime.now(UTC))
    db_session.flush()

    events = repo.list_events(limit=1)
    assert len(events) == 1
    expected_keys = {
        "id",
        "ts",
        "src_ip",
        "dst_port",
        "protocol",
        "event_type",
        "service",
        "country_code",
        "country_name",
        "city",
        "asn",
        "asn_org",
        "campaign_id",
        "schema_version",
    }
    assert set(events[0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# get_unique_public_ips
# ---------------------------------------------------------------------------


def test_get_unique_public_ips_sorted(db_session):
    repo = EventRepository(db_session)
    now = datetime.now(UTC)
    _insert_full_event(repo, str(uuid.uuid4()), now, "10.0.0.1")
    _insert_full_event(repo, str(uuid.uuid4()), now, "1.2.3.4")
    _insert_full_event(repo, str(uuid.uuid4()), now, "5.6.7.8")
    db_session.flush()

    ips = repo.get_unique_public_ips()
    assert ips == sorted(ips)
    assert "1.2.3.4" in ips
    assert "5.6.7.8" in ips


def test_get_unique_public_ips_deduplicates(db_session):
    repo = EventRepository(db_session)
    now = datetime.now(UTC)
    _insert_full_event(repo, str(uuid.uuid4()), now, "1.2.3.4")
    _insert_full_event(repo, str(uuid.uuid4()), now, "1.2.3.4")
    db_session.flush()

    ips = repo.get_unique_public_ips()
    assert ips.count("1.2.3.4") == 1


def test_get_unique_public_ips_excludes_null(db_session):
    """Events with no src_ip must not appear in the IOC feed."""
    repo = EventRepository(db_session)
    eid = str(uuid.uuid4())
    repo.insert_raw_event(
        RawEvent(id=eid, ts="2025-01-01T00:00:00+00:00", source="cowrie", type="auth_failed")
    )
    repo.insert_event(
        HoneypotEvent(
            id=eid,
            ts=datetime(2025, 1, 1, tzinfo=UTC),
            ingested_at=datetime.now(UTC),
            source="cowrie",
            event_type="auth_failed",
            src_ip=None,
        )
    )
    db_session.flush()

    ips = repo.get_unique_public_ips()
    assert ips == []


def test_get_unique_public_ips_empty_db(db_session):
    repo = EventRepository(db_session)
    assert repo.get_unique_public_ips() == []
