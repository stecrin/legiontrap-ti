import os
import sys

# Make 'app' importable from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ui", "backend"))

from fastapi.testclient import TestClient  # type: ignore

from app.main import app  # type: ignore

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_stats_requires_auth():
    r = client.get("/api/stats")  # no header
    assert r.status_code == 401


def test_stats_with_key():
    r = client.get("/api/stats", headers={"x-api-key": "dev-123"})
    assert r.status_code == 200
    body = r.json()
    assert "counts" in body and "total" in body["counts"]


def test_events_requires_auth():
    r = client.get("/api/events")
    assert r.status_code == 401


def test_events_with_valid_key():
    r = client.get("/api/events", headers={"x-api-key": "dev-123"})
    assert r.status_code == 200
    assert "items" in r.json()


def test_cors_allows_configured_origin():
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_blocks_unknown_origin():
    r = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") is None
