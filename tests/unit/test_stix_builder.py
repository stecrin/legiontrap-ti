"""
Unit tests for app/exports/stix.py.

Tests operate on plain Python dicts — no database, no HTTP layer.
"""

from __future__ import annotations

import uuid

import pytest

from app.exports.stix import _stix_id, build_stix_bundle


def _ip_record(
    ip="1.2.3.4",
    first_seen="2026-01-01T00:00:00+00:00",
    last_seen="2026-01-02T00:00:00+00:00",
    event_count=5,
    reputation_score=0.6,
    tags=None,
) -> dict:
    return {
        "ip": ip,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "event_count": event_count,
        "reputation_score": reputation_score,
        # Use explicit sentinel check so tags=[] is preserved as empty list,
        # not substituted with the default.
        "tags": ["brute-force"] if tags is None else tags,
    }


# --- Bundle structure -----------------------------------------------------


def test_bundle_type():
    bundle = build_stix_bundle([])
    assert bundle["type"] == "bundle"


def test_bundle_has_id():
    bundle = build_stix_bundle([])
    assert bundle["id"].startswith("bundle--")


def test_bundle_id_is_valid_uuid():
    bundle_id = build_stix_bundle([])["id"]
    raw = bundle_id.removeprefix("bundle--")
    uuid.UUID(raw)  # raises ValueError if invalid


def test_empty_bundle_has_no_objects():
    bundle = build_stix_bundle([])
    assert bundle["objects"] == []


def test_single_ip_produces_two_objects():
    bundle = build_stix_bundle([_ip_record()])
    assert len(bundle["objects"]) == 2


def test_two_ips_produce_four_objects():
    bundle = build_stix_bundle([_ip_record("1.2.3.4"), _ip_record("5.6.7.8")])
    assert len(bundle["objects"]) == 4


# --- Object types ---------------------------------------------------------


def test_objects_include_ipv4_addr():
    bundle = build_stix_bundle([_ip_record()])
    types = {o["type"] for o in bundle["objects"]}
    assert "ipv4-addr" in types


def test_objects_include_indicator():
    bundle = build_stix_bundle([_ip_record()])
    types = {o["type"] for o in bundle["objects"]}
    assert "indicator" in types


def test_no_campaign_objects():
    bundle = build_stix_bundle([_ip_record()])
    types = {o["type"] for o in bundle["objects"]}
    assert "campaign" not in types


def test_no_relationship_objects():
    bundle = build_stix_bundle([_ip_record()])
    types = {o["type"] for o in bundle["objects"]}
    assert "relationship" not in types


# --- Spec version ---------------------------------------------------------


def test_objects_have_spec_version():
    bundle = build_stix_bundle([_ip_record()])
    for obj in bundle["objects"]:
        assert obj.get("spec_version") == "2.1", f"{obj['type']} missing spec_version"


def test_bundle_has_no_spec_version():
    bundle = build_stix_bundle([])
    assert "spec_version" not in bundle


# --- Deterministic IDs ----------------------------------------------------


def test_same_ip_same_indicator_id():
    bundle1 = build_stix_bundle([_ip_record("10.0.0.1")])
    bundle2 = build_stix_bundle([_ip_record("10.0.0.1")])
    ids1 = {o["id"] for o in bundle1["objects"] if o["type"] == "indicator"}
    ids2 = {o["id"] for o in bundle2["objects"] if o["type"] == "indicator"}
    assert ids1 == ids2


def test_same_ip_same_ipv4_id():
    bundle1 = build_stix_bundle([_ip_record("10.0.0.2")])
    bundle2 = build_stix_bundle([_ip_record("10.0.0.2")])
    ids1 = {o["id"] for o in bundle1["objects"] if o["type"] == "ipv4-addr"}
    ids2 = {o["id"] for o in bundle2["objects"] if o["type"] == "ipv4-addr"}
    assert ids1 == ids2


def test_different_ips_different_indicator_ids():
    bundle = build_stix_bundle([_ip_record("1.1.1.1"), _ip_record("2.2.2.2")])
    indicator_ids = [o["id"] for o in bundle["objects"] if o["type"] == "indicator"]
    assert len(set(indicator_ids)) == 2


def test_stix_id_helper_is_deterministic():
    id1 = _stix_id("indicator", "1.2.3.4")
    id2 = _stix_id("indicator", "1.2.3.4")
    assert id1 == id2


def test_stix_id_format():
    stix_id = _stix_id("indicator", "1.2.3.4")
    assert stix_id.startswith("indicator--")
    raw = stix_id.removeprefix("indicator--")
    uuid.UUID(raw)  # raises ValueError if not a valid UUID


# --- Indicator content ----------------------------------------------------


def test_indicator_pattern():
    bundle = build_stix_bundle([_ip_record("9.9.9.9")])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["pattern"] == "[ipv4-addr:value = '9.9.9.9']"


def test_indicator_pattern_type():
    bundle = build_stix_bundle([_ip_record()])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["pattern_type"] == "stix"


def test_indicator_has_valid_from():
    bundle = build_stix_bundle([_ip_record()])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "valid_from" in indicator


def test_indicator_valid_until_when_last_seen_present():
    bundle = build_stix_bundle([_ip_record(last_seen="2026-06-01T00:00:00+00:00")])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "valid_until" in indicator


def test_indicator_no_valid_until_when_last_seen_absent():
    record = _ip_record()
    record["last_seen"] = None
    bundle = build_stix_bundle([record])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "valid_until" not in indicator


def test_indicator_name_contains_ip():
    bundle = build_stix_bundle([_ip_record("3.3.3.3")])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "3.3.3.3" in indicator["name"]


# --- Labels ---------------------------------------------------------------


def test_brute_force_tag_maps_to_malicious_activity():
    bundle = build_stix_bundle([_ip_record(tags=["brute-force"])])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "malicious-activity" in indicator["labels"]


def test_scanner_tag_maps_to_anomalous_activity():
    bundle = build_stix_bundle([_ip_record(tags=["scanner"])])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "anomalous-activity" in indicator["labels"]


def test_no_tags_defaults_to_malicious_activity():
    record = _ip_record(tags=[])
    bundle = build_stix_bundle([record])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["labels"] == ["malicious-activity"]


def test_none_tags_defaults_to_malicious_activity():
    record = _ip_record(tags=None)
    bundle = build_stix_bundle([record])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["labels"] == ["malicious-activity"]


# --- Confidence -----------------------------------------------------------


def test_confidence_full_score():
    bundle = build_stix_bundle([_ip_record(reputation_score=1.0)])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["confidence"] == 100


def test_confidence_half_score():
    bundle = build_stix_bundle([_ip_record(reputation_score=0.5)])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["confidence"] == 50


def test_confidence_zero_score():
    bundle = build_stix_bundle([_ip_record(reputation_score=0.0)])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["confidence"] == 0


def test_confidence_none_score_defaults_to_50():
    bundle = build_stix_bundle([_ip_record(reputation_score=None)])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["confidence"] == 50


# --- Custom properties ----------------------------------------------------


def test_custom_event_count_present():
    bundle = build_stix_bundle([_ip_record(event_count=17)])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["x_legiontrap_event_count"] == 17


def test_custom_tags_present_when_tags_exist():
    bundle = build_stix_bundle([_ip_record(tags=["brute-force"])])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["x_legiontrap_tags"] == ["brute-force"]


def test_custom_tags_absent_when_no_tags():
    record = _ip_record(tags=[])
    bundle = build_stix_bundle([record])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "x_legiontrap_tags" not in indicator


def test_custom_reputation_score_present():
    bundle = build_stix_bundle([_ip_record(reputation_score=0.7)])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert indicator["x_legiontrap_reputation_score"] == pytest.approx(0.7)


def test_custom_reputation_absent_when_none():
    bundle = build_stix_bundle([_ip_record(reputation_score=None)])
    indicator = next(o for o in bundle["objects"] if o["type"] == "indicator")
    assert "x_legiontrap_reputation_score" not in indicator


# --- IPv4-Addr SCO --------------------------------------------------------


def test_ipv4_addr_value():
    bundle = build_stix_bundle([_ip_record("8.8.8.8")])
    ipv4 = next(o for o in bundle["objects"] if o["type"] == "ipv4-addr")
    assert ipv4["value"] == "8.8.8.8"


def test_ipv4_id_starts_with_type():
    bundle = build_stix_bundle([_ip_record()])
    ipv4 = next(o for o in bundle["objects"] if o["type"] == "ipv4-addr")
    assert ipv4["id"].startswith("ipv4-addr--")


# --- Edge cases -----------------------------------------------------------


def test_record_with_missing_ip_skipped():
    bundle = build_stix_bundle([{"ip": None, "event_count": 1}])
    assert bundle["objects"] == []


def test_record_with_no_ip_key_skipped():
    bundle = build_stix_bundle([{"event_count": 1}])
    assert bundle["objects"] == []
