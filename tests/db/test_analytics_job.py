"""Repository + service tests for campaign analytics population.

Tests use db_session (isolated in-memory SQLite per test) from tests/db/conftest.py.
No HTTP, no app startup.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db.repository import EventRepository
from app.intelligence.analytics import refresh_all_campaign_analytics, refresh_campaign_analytics

_TS = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
_TS_STR = _TS.isoformat()

_IP1 = "10.0.0.1"
_IP2 = "10.0.0.2"
_IP3 = "10.0.0.3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_source_ip(session, ip: str) -> None:
    session.execute(
        text("""
            INSERT OR IGNORE INTO source_ips
                (ip, first_seen, last_seen, event_count)
            VALUES (:ip, :ts, :ts, 0)
        """),
        {"ip": ip, "ts": _TS_STR},
    )
    session.flush()


def _insert_campaign(session, campaign_id: str | None = None, status: str = "active") -> str:
    cid = campaign_id or str(uuid.uuid4())
    EventRepository(session).create_campaign(
        campaign_id=cid,
        name=f"TEST-{cid[:8]}",
        status=status,
        confidence=0.7,
        first_seen=_TS_STR,
        last_seen=_TS_STR,
        member_ip_count=0,
        created_at=_TS_STR,
        updated_at=_TS_STR,
    )
    session.flush()
    return cid


def _add_member(session, campaign_id: str, ip: str) -> None:
    _insert_source_ip(session, ip)
    EventRepository(session).add_campaign_member(
        campaign_id=campaign_id,
        source_ip=ip,
        confidence=0.8,
        added_at=_TS_STR,
        last_active=_TS_STR,
    )
    session.flush()


def _insert_raw_event(session, eid: str, ip: str) -> None:
    session.execute(
        text("""
            INSERT INTO raw_events (id, ts, ingested_at, source, raw_json)
            VALUES (:id, :ts, :ts, :ip, '{}')
        """),
        {"id": eid, "ts": _TS_STR, "ip": ip},
    )
    session.flush()


def _insert_event(
    session,
    eid: str,
    src_ip: str,
    event_type: str = "auth_failed",
    dst_port: int | None = 22,
) -> None:
    _insert_raw_event(session, eid, src_ip)
    session.execute(
        text("""
            INSERT INTO events
                (id, ts, src_ip, dst_port, protocol, event_type, schema_version)
            VALUES (:id, :ts, :src_ip, :dst_port, 'tcp', :event_type, 1)
        """),
        {
            "id": eid,
            "ts": _TS_STR,
            "src_ip": src_ip,
            "dst_port": dst_port,
            "event_type": event_type,
        },
    )
    session.flush()


# ---------------------------------------------------------------------------
# compute_campaign_attack_tactic_dist
# ---------------------------------------------------------------------------


def test_attack_tactic_dist_empty_campaign(db_session):
    cid = _insert_campaign(db_session)
    result = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid)
    assert result == {}


def test_attack_tactic_dist_no_events_for_member(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    result = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid)
    assert result == {}


def test_attack_tactic_dist_single_tactic(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    # auth_failed → Credential Access
    for _ in range(3):
        _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed")
    result = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid)
    assert result == {"Credential Access": 3}


def test_attack_tactic_dist_multiple_tactics(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    # auth_failed → Credential Access (x2), port_scan → Discovery (x3)
    for _ in range(2):
        _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed")
    for _ in range(3):
        _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="port_scan")
    result = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid)
    assert result == {"Discovery": 3, "Credential Access": 2}


def test_attack_tactic_dist_excludes_null_tactic(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    # 'unknown' event_type has NULL attack_tactic
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="unknown")
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed")
    result = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid)
    assert "None" not in result
    assert result == {"Credential Access": 1}


def test_attack_tactic_dist_aggregates_across_members(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    _add_member(db_session, cid, _IP2)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed")
    _insert_event(db_session, str(uuid.uuid4()), _IP2, event_type="auth_failed")
    _insert_event(db_session, str(uuid.uuid4()), _IP2, event_type="port_scan")
    result = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid)
    assert result == {"Credential Access": 2, "Discovery": 1}


def test_attack_tactic_dist_only_counts_own_members(db_session):
    cid1 = _insert_campaign(db_session)
    cid2 = _insert_campaign(db_session)
    _add_member(db_session, cid1, _IP1)
    _add_member(db_session, cid2, _IP2)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed")
    _insert_event(db_session, str(uuid.uuid4()), _IP2, event_type="port_scan")
    r1 = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid1)
    r2 = EventRepository(db_session).compute_campaign_attack_tactic_dist(cid2)
    assert r1 == {"Credential Access": 1}
    assert r2 == {"Discovery": 1}


# ---------------------------------------------------------------------------
# compute_campaign_top_target_ports
# ---------------------------------------------------------------------------


def test_top_target_ports_empty_campaign(db_session):
    cid = _insert_campaign(db_session)
    result = EventRepository(db_session).compute_campaign_top_target_ports(cid)
    assert result == []


def test_top_target_ports_no_events_for_member(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    result = EventRepository(db_session).compute_campaign_top_target_ports(cid)
    assert result == []


def test_top_target_ports_single_port(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    for _ in range(4):
        _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=22)
    result = EventRepository(db_session).compute_campaign_top_target_ports(cid)
    assert result == [{"port": 22, "count": 4}]


def test_top_target_ports_ordered_by_count_desc(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=80)
    for _ in range(3):
        _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=22)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=443)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=443)
    result = EventRepository(db_session).compute_campaign_top_target_ports(cid)
    ports = [r["port"] for r in result]
    counts = [r["count"] for r in result]
    assert ports[0] == 22
    assert counts[0] == 3
    assert counts == sorted(counts, reverse=True)


def test_top_target_ports_capped_at_top_n(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    for port in [22, 80, 443, 8080, 3306, 5432, 21]:
        _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=port)
    result = EventRepository(db_session).compute_campaign_top_target_ports(cid, top_n=5)
    assert len(result) == 5


def test_top_target_ports_excludes_null_port(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=None)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=22)
    result = EventRepository(db_session).compute_campaign_top_target_ports(cid)
    assert all(r["port"] is not None for r in result)
    assert len(result) == 1


def test_top_target_ports_aggregates_across_members(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    _add_member(db_session, cid, _IP2)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, dst_port=22)
    _insert_event(db_session, str(uuid.uuid4()), _IP2, dst_port=22)
    result = EventRepository(db_session).compute_campaign_top_target_ports(cid)
    assert result == [{"port": 22, "count": 2}]


# ---------------------------------------------------------------------------
# update_campaign_analytics
# ---------------------------------------------------------------------------


def test_update_campaign_analytics_persists_json(db_session):
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.update_campaign_analytics(
        campaign_id=cid,
        attack_tactic_dist='{"Credential Access": 5}',
        top_target_ports='[{"port": 22, "count": 5}]',
        updated_at=_TS_STR,
    )
    db_session.flush()
    row = db_session.execute(
        text("SELECT attack_tactic_dist, top_target_ports FROM campaigns WHERE id = :id"),
        {"id": cid},
    ).fetchone()
    assert row[0] == '{"Credential Access": 5}'
    assert row[1] == '[{"port": 22, "count": 5}]'


def test_update_campaign_analytics_accepts_null(db_session):
    cid = _insert_campaign(db_session)
    repo = EventRepository(db_session)
    repo.update_campaign_analytics(
        campaign_id=cid,
        attack_tactic_dist=None,
        top_target_ports=None,
        updated_at=_TS_STR,
    )
    db_session.flush()
    row = db_session.execute(
        text("SELECT attack_tactic_dist, top_target_ports FROM campaigns WHERE id = :id"),
        {"id": cid},
    ).fetchone()
    assert row[0] is None
    assert row[1] is None


# ---------------------------------------------------------------------------
# refresh_campaign_analytics (service layer)
# ---------------------------------------------------------------------------


def test_refresh_campaign_analytics_populates_fields(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed", dst_port=22)
    db_session.commit()

    result = refresh_campaign_analytics(EventRepository(db_session), cid)

    assert result["attack_tactic_dist"] == {"Credential Access": 1}
    assert result["top_target_ports"] == [{"port": 22, "count": 1}]

    row = db_session.execute(
        text("SELECT attack_tactic_dist, top_target_ports FROM campaigns WHERE id = :id"),
        {"id": cid},
    ).fetchone()
    assert json.loads(row[0]) == {"Credential Access": 1}
    assert json.loads(row[1]) == [{"port": 22, "count": 1}]


def test_refresh_campaign_analytics_empty_campaign_sets_null(db_session):
    cid = _insert_campaign(db_session)
    db_session.commit()
    result = refresh_campaign_analytics(EventRepository(db_session), cid)
    assert result["attack_tactic_dist"] == {}
    assert result["top_target_ports"] == []
    row = db_session.execute(
        text("SELECT attack_tactic_dist, top_target_ports FROM campaigns WHERE id = :id"),
        {"id": cid},
    ).fetchone()
    assert row[0] is None
    assert row[1] is None


def test_refresh_campaign_analytics_idempotent(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="port_scan", dst_port=80)
    db_session.commit()

    repo = EventRepository(db_session)
    r1 = refresh_campaign_analytics(repo, cid)
    db_session.commit()
    r2 = refresh_campaign_analytics(repo, cid)
    db_session.commit()

    assert r1["attack_tactic_dist"] == r2["attack_tactic_dist"]
    assert r1["top_target_ports"] == r2["top_target_ports"]


def test_refresh_campaign_analytics_injectable_now(db_session):
    cid = _insert_campaign(db_session)
    db_session.commit()
    fixed_now = datetime(2025, 1, 15, 0, 0, 0, tzinfo=UTC)
    refresh_campaign_analytics(EventRepository(db_session), cid, now=fixed_now)
    db_session.commit()
    row = db_session.execute(
        text("SELECT updated_at FROM campaigns WHERE id = :id"), {"id": cid}
    ).fetchone()
    assert row[0] == fixed_now.isoformat()


# ---------------------------------------------------------------------------
# refresh_all_campaign_analytics (service layer)
# ---------------------------------------------------------------------------


def test_refresh_all_returns_count(db_session):
    _insert_campaign(db_session)
    _insert_campaign(db_session)
    db_session.commit()
    result = refresh_all_campaign_analytics(EventRepository(db_session))
    assert result["campaigns_updated"] == 2
    assert "refreshed_at" in result


def test_refresh_all_zero_campaigns(db_session):
    result = refresh_all_campaign_analytics(EventRepository(db_session))
    assert result["campaigns_updated"] == 0


def test_refresh_all_updates_all_campaigns(db_session):
    cid1 = _insert_campaign(db_session)
    cid2 = _insert_campaign(db_session)
    _add_member(db_session, cid1, _IP1)
    _add_member(db_session, cid2, _IP2)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed", dst_port=22)
    _insert_event(db_session, str(uuid.uuid4()), _IP2, event_type="port_scan", dst_port=80)
    db_session.commit()

    refresh_all_campaign_analytics(EventRepository(db_session))
    db_session.commit()

    r1 = EventRepository(db_session).get_campaign(cid1)
    r2 = EventRepository(db_session).get_campaign(cid2)

    assert r1["attack_tactic_dist"] is not None
    assert r2["attack_tactic_dist"] is not None
    assert json.loads(r1["attack_tactic_dist"]) == {"Credential Access": 1}
    assert json.loads(r2["attack_tactic_dist"]) == {"Discovery": 1}


def test_refresh_all_includes_historical_campaigns(db_session):
    _insert_campaign(db_session, status="historical")
    db_session.commit()
    result = refresh_all_campaign_analytics(EventRepository(db_session))
    assert result["campaigns_updated"] == 1


def test_refresh_all_idempotent(db_session):
    cid = _insert_campaign(db_session)
    _add_member(db_session, cid, _IP1)
    _insert_event(db_session, str(uuid.uuid4()), _IP1, event_type="auth_failed", dst_port=22)
    db_session.commit()

    repo = EventRepository(db_session)
    r1 = refresh_all_campaign_analytics(repo)
    db_session.commit()
    r2 = refresh_all_campaign_analytics(repo)
    db_session.commit()

    assert r1["campaigns_updated"] == r2["campaigns_updated"]
    campaign = repo.get_campaign(cid)
    assert campaign["attack_tactic_dist"] is not None
