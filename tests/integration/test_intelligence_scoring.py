"""
Integration tests: source IP caching lifecycle and intelligence scoring/tagging.

Tests hit the full HTTP → router → repository → in-memory SQLite stack.
Schema is bootstrapped by tests/conftest.py; rows are reset per test by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.routers.ingest as ingest_module
import app.utils.geoip as geoip_module
from app.db.connection import get_engine
from app.main import app
from app.utils.geoip import reset_reader_for_testing

client = TestClient(app)
API_KEY = "dev-123"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

PUBLIC_IP = "8.8.8.8"
OTHER_PUBLIC_IP = "1.1.1.1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    event_id: str | None = None,
    raw_type: str = "cowrie.login.failed",
    source: str = "cowrie",
    ip: str = PUBLIC_IP,
) -> dict:
    return {
        "id": event_id or str(uuid.uuid4()),
        "ts": "2025-10-28T18:31:08+00:00",
        "source": source,
        "type": raw_type,
        "data": {"ip": ip},
    }


def _ingest(*events):
    return client.post("/api/ingest", json={"events": list(events)}, headers=HEADERS)


def _get_source_ip_row(ip: str) -> dict | None:
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT event_count, tags, reputation_score, country_code "
                "FROM source_ips WHERE ip = :ip"
            ),
            {"ip": ip},
        ).fetchone()
    if row is None:
        return None
    return {
        "event_count": row[0],
        "tags": json.loads(row[1]) if row[1] else [],
        "reputation_score": row[2],
        "country_code": row[3],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_geoip_reader():
    reset_reader_for_testing()
    yield
    reset_reader_for_testing()


@pytest.fixture()
def no_mmdb(monkeypatch, tmp_path):
    """Ensure mmdb is absent and enrich_ip returns all-None for every test."""
    monkeypatch.setattr(geoip_module, "CITY_DB_PATH", tmp_path / "absent.mmdb")


# ---------------------------------------------------------------------------
# Caching lifecycle tests
# ---------------------------------------------------------------------------


def test_cache_miss_calls_enrich_ip_once(no_mmdb, monkeypatch):
    """First event from an unknown IP must call enrich_ip exactly once."""
    call_count = [0]

    def counting_enrich(ip):
        call_count[0] += 1
        return {"country_code": None, "country_name": None, "city": None}

    monkeypatch.setattr(ingest_module, "enrich_ip", counting_enrich)

    resp = _ingest(_event("cache-miss-1"))
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1
    assert call_count[0] == 1


def test_cache_hit_skips_enrich_ip(no_mmdb, monkeypatch):
    """Second event from the same IP must NOT call enrich_ip.

    The counting stub returns a real country_code so that the source_ips row is
    populated on first insert. The second event then finds it via get_source_ip_geo
    (which requires country_code IS NOT NULL) and skips the file lookup entirely.
    """
    call_count = [0]

    def counting_enrich(ip):
        call_count[0] += 1
        return {"country_code": "US", "country_name": "United States", "city": "Mountain View"}

    monkeypatch.setattr(ingest_module, "enrich_ip", counting_enrich)

    _ingest(_event("cache-hit-first"))
    assert call_count[0] == 1  # cache miss on first event

    _ingest(_event("cache-hit-second"))
    assert call_count[0] == 1  # cache hit on second event — no additional call


def test_different_ips_each_call_enrich_ip(no_mmdb, monkeypatch):
    """Each distinct IP gets its own enrich_ip call."""
    call_count = [0]

    def counting_enrich(ip):
        call_count[0] += 1
        return {"country_code": None, "country_name": None, "city": None}

    monkeypatch.setattr(ingest_module, "enrich_ip", counting_enrich)

    _ingest(
        _event("diff-ip-1", ip=PUBLIC_IP),
        _event("diff-ip-2", ip=OTHER_PUBLIC_IP),
    )
    assert call_count[0] == 2


def test_get_source_ip_geo_returns_none_for_unknown_ip():
    """get_source_ip_geo returns None when IP has no source_ips row."""
    from app.db.connection import get_session
    from app.db.repository import EventRepository

    with get_session() as session:
        repo = EventRepository(session)
        result = repo.get_source_ip_geo("203.0.113.99")
    assert result is None


def test_get_source_ip_geo_returns_none_if_country_null(no_mmdb):
    """get_source_ip_geo returns None for a known IP with NULL country_code."""
    _ingest(_event("geo-null-test"))
    from app.db.connection import get_session
    from app.db.repository import EventRepository

    with get_session() as session:
        repo = EventRepository(session)
        result = repo.get_source_ip_geo(PUBLIC_IP)
    assert result is None


# ---------------------------------------------------------------------------
# Tagging tests
# ---------------------------------------------------------------------------


def test_brute_force_tag_applied_after_auth_failed(no_mmdb):
    _ingest(_event("tag-bf-1", raw_type="cowrie.login.failed"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert "brute-force" in row["tags"]


def test_auth_success_tag_applied(no_mmdb):
    _ingest(_event("tag-as-1", raw_type="cowrie.login.success"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert "auth-success" in row["tags"]


def test_scanner_tag_applied_after_port_scan(no_mmdb):
    _ingest(_event("tag-scan-1", raw_type="dionaea.connection.free", source="dionaea"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert "scanner" in row["tags"]


def test_command_exec_tag_applied(no_mmdb):
    _ingest(_event("tag-cmd-1", raw_type="cowrie.command.input"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert "command-exec" in row["tags"]


def test_malware_tag_applied(no_mmdb):
    _ingest(_event("tag-mal-1", raw_type="cowrie.session.file_upload"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert "malware" in row["tags"]


def test_tags_are_additive_across_events(no_mmdb):
    """Tags accumulated over multiple events are never removed."""
    _ingest(_event("additive-1", raw_type="cowrie.login.failed"))
    _ingest(_event("additive-2", raw_type="dionaea.connection.free", source="dionaea"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert "brute-force" in row["tags"]
    assert "scanner" in row["tags"]


def test_unknown_event_type_does_not_add_tag(no_mmdb):
    _ingest(_event("unknown-type-1", raw_type="some.unknown.type", source="custom"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert row["tags"] == []


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


def test_reputation_score_set_after_auth_failed(no_mmdb):
    _ingest(_event("score-bf-1", raw_type="cowrie.login.failed"))
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert row["reputation_score"] is not None
    assert row["reputation_score"] > 0.0


def test_reputation_score_meets_exit_criterion(no_mmdb):
    """Blueprint exit criterion: 100+ auth_failed events → reputation_score >= 0.4."""
    events = [_event(f"exit-criterion-{i}", raw_type="cowrie.login.failed") for i in range(100)]
    _ingest(*events)
    row = _get_source_ip_row(PUBLIC_IP)
    assert row is not None
    assert "brute-force" in row["tags"]
    assert row["reputation_score"] >= 0.4


def test_reputation_score_increases_with_event_count(no_mmdb):
    """Score after 100 events must be higher than score after 1 event."""
    _ingest(_event("score-low-1", raw_type="cowrie.login.failed"))
    row_low = _get_source_ip_row(PUBLIC_IP)

    for i in range(99):
        _ingest(_event(f"score-high-{i}", raw_type="cowrie.login.failed", ip=OTHER_PUBLIC_IP))

    row_high = _get_source_ip_row(OTHER_PUBLIC_IP)
    assert row_high["reputation_score"] > row_low["reputation_score"]


def test_scoring_failure_does_not_block_ingest(no_mmdb, monkeypatch):
    """A scoring error must not cause ingest to return non-200."""
    from app.db import repository as repo_module

    def exploding_update(self, ip, tags, score):
        raise RuntimeError("simulated scoring failure")

    monkeypatch.setattr(
        repo_module.EventRepository, "update_source_ip_intelligence", exploding_update
    )

    resp = _ingest(_event("score-fail-1", raw_type="cowrie.login.failed"))
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 1
