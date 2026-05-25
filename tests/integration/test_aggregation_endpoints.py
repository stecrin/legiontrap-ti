"""
Integration tests for GET /api/intelligence/top-countries and
GET /api/intelligence/top-asns.

Rows are inserted directly into source_ips for deterministic control
over country_code, asn, and event_count without requiring GeoIP MMDB.
Schema is bootstrapped by tests/conftest.py; rows reset by
tests/integration/conftest.py (reset_db_rows fixture).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.connection import get_engine
from app.main import app

client = TestClient(app)
HEADERS = {"x-api-key": "dev-123"}

_TS_EARLY = "2025-01-01T00:00:00+00:00"
_TS_LATE = "2025-06-01T00:00:00+00:00"

_COUNTRY_FIELDS = {
    "country_code",
    "country_name",
    "event_count",
    "unique_ips",
    "first_seen",
    "last_seen",
}
_ASN_FIELDS = {"asn", "asn_org", "event_count", "unique_ips", "first_seen", "last_seen"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert(
    ip: str,
    event_count: int = 1,
    country_code: str | None = None,
    country_name: str | None = None,
    asn: int | None = None,
    asn_org: str | None = None,
    first_seen: str = _TS_EARLY,
    last_seen: str = _TS_LATE,
) -> None:
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT OR IGNORE INTO source_ips
                    (ip, first_seen, last_seen, event_count,
                     country_code, country_name, asn, asn_org)
                VALUES
                    (:ip, :fs, :ls, :ec, :cc, :cn, :asn, :ao)
                """),
            {
                "ip": ip,
                "fs": first_seen,
                "ls": last_seen,
                "ec": event_count,
                "cc": country_code,
                "cn": country_name,
                "asn": asn,
                "ao": asn_org,
            },
        )
        conn.commit()


# ---------------------------------------------------------------------------
# GET /api/intelligence/top-countries
# ---------------------------------------------------------------------------


def test_top_countries_empty_db():
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_top_countries_returns_required_fields():
    _insert("1.0.0.1", country_code="US", country_name="United States")
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    item = resp.json()["items"][0]
    assert _COUNTRY_FIELDS.issubset(item.keys())


def test_top_countries_aggregates_event_count():
    """Two IPs from the same country — event_counts must be summed."""
    _insert("2.0.0.1", event_count=30, country_code="CN", country_name="China")
    _insert("2.0.0.2", event_count=20, country_code="CN", country_name="China")
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    items = resp.json()["items"]
    cn = next(i for i in items if i["country_code"] == "CN")
    assert cn["event_count"] == 50


def test_top_countries_unique_ips_count():
    """unique_ips must reflect distinct IP count per country."""
    _insert("3.0.0.1", country_code="DE", country_name="Germany")
    _insert("3.0.0.2", country_code="DE", country_name="Germany")
    _insert("3.0.0.3", country_code="DE", country_name="Germany")
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    items = resp.json()["items"]
    de = next(i for i in items if i["country_code"] == "DE")
    assert de["unique_ips"] == 3


def test_top_countries_sorted_by_event_count_desc():
    _insert("4.0.0.1", event_count=5, country_code="FR", country_name="France")
    _insert("4.0.0.2", event_count=100, country_code="RU", country_name="Russia")
    _insert("4.0.0.3", event_count=50, country_code="BR", country_name="Brazil")
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    counts = [i["event_count"] for i in resp.json()["items"]]
    assert counts == sorted(counts, reverse=True)


def test_top_countries_null_country_excluded():
    """IPs with NULL country_code must not appear in the aggregation."""
    _insert("5.0.0.1", country_code=None)
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    assert resp.json()["items"] == []


def test_top_countries_mixed_null_and_known():
    """NULL-country IPs are excluded; known-country IPs appear normally."""
    _insert("6.0.0.1", event_count=10, country_code="JP", country_name="Japan")
    _insert("6.0.0.2", event_count=5, country_code=None)
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["country_code"] == "JP"


def test_top_countries_first_seen_is_earliest():
    _insert(
        "7.0.0.1", country_code="KR", first_seen="2025-03-01T00:00:00+00:00", last_seen=_TS_LATE
    )
    _insert(
        "7.0.0.2", country_code="KR", first_seen="2025-01-01T00:00:00+00:00", last_seen=_TS_LATE
    )
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    kr = next(i for i in resp.json()["items"] if i["country_code"] == "KR")
    assert kr["first_seen"] == "2025-01-01T00:00:00+00:00"


def test_top_countries_last_seen_is_latest():
    _insert(
        "8.0.0.1", country_code="AU", first_seen=_TS_EARLY, last_seen="2025-04-01T00:00:00+00:00"
    )
    _insert(
        "8.0.0.2", country_code="AU", first_seen=_TS_EARLY, last_seen="2025-08-01T00:00:00+00:00"
    )
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    au = next(i for i in resp.json()["items"] if i["country_code"] == "AU")
    assert au["last_seen"] == "2025-08-01T00:00:00+00:00"


def test_top_countries_limit_respected():
    for i in range(5):
        _insert(f"9.0.0.{i + 1}", country_code=f"C{i}", country_name=f"Country{i}")
    resp = client.get("/api/intelligence/top-countries?limit=3", headers=HEADERS)
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["count"] == 3


def test_top_countries_count_matches_items():
    _insert("10.0.0.1", country_code="NL", country_name="Netherlands")
    _insert("10.0.0.2", country_code="SE", country_name="Sweden")
    resp = client.get("/api/intelligence/top-countries", headers=HEADERS)
    data = resp.json()
    assert data["count"] == len(data["items"])


def test_top_countries_limit_below_min_returns_422():
    resp = client.get("/api/intelligence/top-countries?limit=0", headers=HEADERS)
    assert resp.status_code == 422


def test_top_countries_limit_above_max_returns_422():
    resp = client.get("/api/intelligence/top-countries?limit=101", headers=HEADERS)
    assert resp.status_code == 422


def test_top_countries_no_auth_returns_401():
    resp = client.get("/api/intelligence/top-countries")
    assert resp.status_code == 401


def test_top_countries_wrong_key_returns_401():
    resp = client.get("/api/intelligence/top-countries", headers={"x-api-key": "bad"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/intelligence/top-asns
# ---------------------------------------------------------------------------


def test_top_asns_empty_db():
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["count"] == 0


def test_top_asns_returns_required_fields():
    _insert("11.0.0.1", asn=15169, asn_org="GOOGLE")
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    item = resp.json()["items"][0]
    assert _ASN_FIELDS.issubset(item.keys())


def test_top_asns_aggregates_event_count():
    """Two IPs from the same ASN — event_counts must be summed."""
    _insert("12.0.0.1", event_count=40, asn=4134, asn_org="CHINANET")
    _insert("12.0.0.2", event_count=60, asn=4134, asn_org="CHINANET")
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    items = resp.json()["items"]
    asn_item = next(i for i in items if i["asn"] == 4134)
    assert asn_item["event_count"] == 100


def test_top_asns_unique_ips_count():
    _insert("13.0.0.1", asn=7922, asn_org="COMCAST")
    _insert("13.0.0.2", asn=7922, asn_org="COMCAST")
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    items = resp.json()["items"]
    asn_item = next(i for i in items if i["asn"] == 7922)
    assert asn_item["unique_ips"] == 2


def test_top_asns_sorted_by_event_count_desc():
    _insert("14.0.0.1", event_count=10, asn=1001, asn_org="ASN-A")
    _insert("14.0.0.2", event_count=500, asn=1002, asn_org="ASN-B")
    _insert("14.0.0.3", event_count=75, asn=1003, asn_org="ASN-C")
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    counts = [i["event_count"] for i in resp.json()["items"]]
    assert counts == sorted(counts, reverse=True)


def test_top_asns_null_asn_excluded():
    _insert("15.0.0.1", asn=None)
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    assert resp.json()["items"] == []


def test_top_asns_mixed_null_and_known():
    _insert("16.0.0.1", event_count=20, asn=2001, asn_org="KNOWN-ASN")
    _insert("16.0.0.2", asn=None)
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["asn"] == 2001


def test_top_asns_asn_org_can_be_null():
    """asn_org may be NULL in source_ips — must be returned as null, not error."""
    _insert("17.0.0.1", asn=9999, asn_org=None)
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["asn"] == 9999
    assert item["asn_org"] is None


def test_top_asns_first_seen_is_earliest():
    _insert("18.0.0.1", asn=3001, first_seen="2025-05-01T00:00:00+00:00", last_seen=_TS_LATE)
    _insert("18.0.0.2", asn=3001, first_seen="2025-02-01T00:00:00+00:00", last_seen=_TS_LATE)
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    asn_item = next(i for i in resp.json()["items"] if i["asn"] == 3001)
    assert asn_item["first_seen"] == "2025-02-01T00:00:00+00:00"


def test_top_asns_last_seen_is_latest():
    _insert("19.0.0.1", asn=4001, first_seen=_TS_EARLY, last_seen="2025-03-01T00:00:00+00:00")
    _insert("19.0.0.2", asn=4001, first_seen=_TS_EARLY, last_seen="2025-09-01T00:00:00+00:00")
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    asn_item = next(i for i in resp.json()["items"] if i["asn"] == 4001)
    assert asn_item["last_seen"] == "2025-09-01T00:00:00+00:00"


def test_top_asns_limit_respected():
    for i in range(5):
        _insert(f"20.0.0.{i + 1}", asn=5000 + i, asn_org=f"ASN-{i}")
    resp = client.get("/api/intelligence/top-asns?limit=2", headers=HEADERS)
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["count"] == 2


def test_top_asns_count_matches_items():
    _insert("21.0.0.1", asn=6001, asn_org="A")
    _insert("21.0.0.2", asn=6002, asn_org="B")
    resp = client.get("/api/intelligence/top-asns", headers=HEADERS)
    data = resp.json()
    assert data["count"] == len(data["items"])


def test_top_asns_limit_below_min_returns_422():
    resp = client.get("/api/intelligence/top-asns?limit=0", headers=HEADERS)
    assert resp.status_code == 422


def test_top_asns_limit_above_max_returns_422():
    resp = client.get("/api/intelligence/top-asns?limit=101", headers=HEADERS)
    assert resp.status_code == 422


def test_top_asns_no_auth_returns_401():
    resp = client.get("/api/intelligence/top-asns")
    assert resp.status_code == 401


def test_top_asns_wrong_key_returns_401():
    resp = client.get("/api/intelligence/top-asns", headers={"x-api-key": "bad"})
    assert resp.status_code == 401
