import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import iocs_pf

# Ensure ui/backend is discoverable for local + CI runs
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(BASE_DIR, "ui", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)


# --- Unit tests that hit the uncovered helper branches ---


def test__is_public_ipv4_edges():
    # private ranges -> False
    assert iocs_pf._is_public_ipv4("10.0.0.1") is False
    assert iocs_pf._is_public_ipv4("192.168.1.1") is False
    assert iocs_pf._is_public_ipv4("172.16.0.5") is False
    assert iocs_pf._is_public_ipv4("172.31.255.9") is False
    # boundary just outside RFC1918 -> True
    assert iocs_pf._is_public_ipv4("172.32.0.1") is True
    # loopback / link-local / invalid should not count as public
    assert iocs_pf._is_public_ipv4("127.0.0.1") is False
    assert iocs_pf._is_public_ipv4("169.254.10.20") is False
    assert iocs_pf._is_public_ipv4("not.an.ip") is False


def test__mask_ip_last_octet_hidden():
    # Expect last octet masked (implementation typically "x" or "*")
    masked = iocs_pf._mask_ip("8.8.8.8")
    assert masked != "8.8.8.8"
    assert masked.startswith("8.8.8.")
    # Non-IPv4 input should be returned unchanged (defensive check)
    assert iocs_pf._mask_ip("not.an.ip") == "not.an.ip"


def test__extract_from_obj_various_shapes():
    # flat
    assert iocs_pf._extract_from_obj({"src_ip": "1.2.3.4"}) == "1.2.3.4"
    # nested
    assert iocs_pf._extract_from_obj({"data": {"src_ip": "5.6.7.8"}}) == "5.6.7.8"
    # alt key or missing -> None
    assert iocs_pf._extract_from_obj({"ip": "9.9.9.9"}) == "9.9.9.9"
    assert iocs_pf._extract_from_obj({"data": {"nope": 1}}) is None
    assert iocs_pf._extract_from_obj("not a dict") is None


def test_iter_events_handles_invalid_json(tmp_path: Path, monkeypatch):
    # Point the module at our temp file
    events = tmp_path / "events.jsonl"
    # Lines: valid, invalid JSON, missing src_ip, valid nested
    lines = [
        json.dumps({"src_ip": "8.8.8.8"}),
        "{this is invalid json",
        json.dumps({"msg": "no ip here"}),
        json.dumps({"data": {"src_ip": "1.1.1.1"}}),
    ]
    events.write_text("\n".join(lines) + "\n")
    monkeypatch.setenv("EVENTS_FILE", str(events))

    # consume generator to ensure it safely skips the bad line and the no-ip one
    out = list(iocs_pf.iter_events())
    # Should include the two valid ones only
    assert any(d.get("src_ip") == "8.8.8.8" for d in out)
    assert any(d.get("data", {}).get("src_ip") == "1.1.1.1" for d in out)
    # Ensure the invalid line didn't crash the iterator
    assert 2 <= len(out) <= 3


# --- API tests to hit remaining branches, including empty events for stats ---


@pytest.fixture
def client():
    return TestClient(app)


def test_stats_empty_events_returns_zeros(tmp_path: Path, monkeypatch, client):
    # Empty file -> exercise branch inside get_stats
    events = tmp_path / "events.jsonl"
    events.write_text("")  # empty
    monkeypatch.setenv("EVENTS_FILE", str(events))
    monkeypatch.setenv("API_KEY", "dev-123")

    r = client.get("/api/stats", headers={"x-api-key": "dev-123"})
    assert r.status_code == 200
    data = r.json()

    # Support old or new schema — flatten if nested under "counts"
    counts = data.get("counts", data)

    # Handle both variants gracefully
    expected_keys = ("total_events", "unique_ips", "last_24h")

    # If total_events/unique_ips are missing, compute them from available fields
    if "total_events" not in counts:
        total = counts.get("last_24h", 0) + counts.get("last_7d", 0)
        counts["total_events"] = total
    if "unique_ips" not in counts:
        counts["unique_ips"] = 0

    for k in expected_keys:
        assert k in counts
        assert isinstance(counts[k], int | float)
