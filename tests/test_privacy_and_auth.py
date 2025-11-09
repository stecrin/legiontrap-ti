# ----------------------------------------------------------------------
# tests/test_privacy_and_auth.py
# Unit tests for API key enforcement and privacy mode behavior.
# These validate the /api/iocs endpoints and ensure privacy masking logic
# works as intended when PRIVACY_MODE is enabled.
# ----------------------------------------------------------------------

import json
import os
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
    """Ensure privacy mode anonymizes IPs in exported lists."""
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setenv("PRIVACY_MODE", "true")
    monkeypatch.setenv("FEED_SALT", "unit-test-salt")

    # Create a temporary events file with one IP
    os.makedirs("storage", exist_ok=True)
    path = "storage/events.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ip": "8.8.8.8"}) + "\n")

    reload(main)
    client = TestClient(main.app)

    # Request UFW export
    r = client.get("/api/iocs/ufw.txt", headers={"x-api-key": "secret"})
    assert r.status_code == 200
    body = r.text.strip()
    assert "8.8.8.8" not in body  # IP should be hashed
    assert "deny from ip-" in body  # Hashed prefix present

    # Request PF export
    r = client.get("/api/iocs/pf.conf", headers={"x-api-key": "secret"})
    assert r.status_code == 200
    body = r.text.strip()
    assert "8.8.8.8" not in body
    assert "ip-" in body
