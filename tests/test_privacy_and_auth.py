# ----------------------------------------------------------------------
# tests/test_privacy_and_auth.py
# Unit tests for API key enforcement and privacy mode behavior.
# These validate the /api/iocs endpoints and ensure privacy masking logic
# works as intended when PRIVACY_MODE is enabled.
# ----------------------------------------------------------------------

from importlib import reload

from fastapi.testclient import TestClient

import app.main as main


def test_api_key_required(monkeypatch):
    """Ensure endpoints reject missing or invalid API key."""
    # Patch the API_KEY environment variable to simulate protection
    monkeypatch.setenv("API_KEY", "secret")

    # Reload app to apply the env var
    reload(main)
    client = TestClient(main.app)

    # 1️⃣ Missing key → should be 401
    r = client.get("/api/iocs/pf.conf")
    assert r.status_code == 401

    # 2️⃣ Wrong key → should be 401
    r = client.get("/api/iocs/ufw.txt", headers={"x-api-key": "wrong"})
    assert r.status_code == 401


def test_privacy_mode_hashes_outputs(monkeypatch):
    """Privacy mode must hash IPs in IOC exports.

    SQLite is empty so the endpoint uses the built-in "1.2.3.4" fallback;
    privacy mode must hash even the fallback IP.
    """
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setenv("PRIVACY_MODE", "true")
    monkeypatch.setenv("FEED_SALT", "unit-test-salt")

    reload(main)
    client = TestClient(main.app)

    # UFW export — fallback IP must be hashed, not exposed
    r = client.get("/api/iocs/ufw.txt", headers={"x-api-key": "secret"})
    assert r.status_code == 200
    body = r.text.strip()
    assert "8.8.8.8" not in body
    assert "deny from ip-" in body

    # PF export — same expectation
    r = client.get("/api/iocs/pf.conf", headers={"x-api-key": "secret"})
    assert r.status_code == 200
    body = r.text.strip()
    assert "8.8.8.8" not in body
    assert "ip-" in body
