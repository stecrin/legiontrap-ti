# ruff: noqa: E402  (we intentionally adjust sys.path before imports)
import pathlib
import sys

# Ensure repo root is on sys.path so "app" package resolves
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib
import json
import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.iocs_pf as iocs_pf  # import module form for reload()

H = {"x-api-key": "dev-123"}

EVENTS = [
    {"src_ip": "10.0.0.1"},  # private -> filtered
    {"source_ip": "203.0.113.10"},  # TEST-NET-3 (non-global) -> filtered (is_global=False)
    {"ip": "8.8.8.8"},  # global -> kept
    {"client_ip": "1.1.1.1"},  # global -> kept / masked in privacy mode
    {"message": "failed from 192.168.1.7"},  # private -> filtered
]


def write_events(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for e in EVENTS:
            f.write(json.dumps(e) + "\n")


def build_client(monkeypatch, events_path: str, privacy: str | None) -> TestClient:
    # Point the router at our temp file
    monkeypatch.setenv("EVENTS_PATH", events_path)
    # Make sure any API-key check matches our header (if your app checks env)
    for k in ("API_KEY", "LEGION_API_KEY", "APP_API_KEY"):
        monkeypatch.setenv(k, "dev-123")
    if privacy is None:
        monkeypatch.delenv("PRIVACY_MODE", raising=False)
    else:
        monkeypatch.setenv("PRIVACY_MODE", privacy)

    # Reload module so it re-reads PRIVACY_MODE (and other env) at import time
    importlib.reload(iocs_pf)

    app = FastAPI()
    app.include_router(iocs_pf.router)  # only the router under test
    return TestClient(app)


def test_pf_conf_filters_non_public(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        events_path = os.path.join(td, "events.jsonl")
        write_events(events_path)
        client = build_client(monkeypatch, events_path, privacy=None)

        r = client.get("/api/iocs/pf.conf", headers=H)
        assert r.status_code == 200
        body = r.text
        # Only global IPs present
        assert "8.8.8.8" in body
        assert "1.1.1.1" in body
        # filtered ones
        assert "10.0.0.1" not in body
        assert "192.168.1.7" not in body
        assert "203.0.113.10" not in body  # not global


def test_privacy_mode_masks_ips(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        events_path = os.path.join(td, "events.jsonl")
        write_events(events_path)
        client = build_client(monkeypatch, events_path, privacy="on")

        r = client.get("/api/iocs/pf.conf", headers=H)
        assert r.status_code == 200
        body = r.text
        # masked
        assert "8.8.8.x" in body
        assert "1.1.1.x" in body
        # raw must not appear
        assert "8.8.8.8" not in body
        assert "1.1.1.1" not in body
