#!/usr/bin/env bash
set -euo pipefail

# Base API URL and auth header (can be overridden via env vars)
BASE=${BASE:-http://127.0.0.1:8088}
H=${H:-"x-api-key: dev-123"}

# Helper to post a single JSON event (prints a dot if OK)
post() {
  curl -fsS -X POST "$BASE/api/ingest" \
    -H "$H" -H 'Content-Type: application/json' \
    -d "$1" >/dev/null && printf "."
}

echo -n "Seeding"
post '{"source":"cowrie","eventid":"cowrie.login.failed","username":"root","password":"123456","src_ip":"203.0.113.10"}'
post '{"source":"cowrie","eventid":"cowrie.login.failed","username":"admin","password":"admin","src_ip":"203.0.113.11"}'
post '{"source":"opencanary","eventid":"canary.login.failed","username":"pi","password":"raspberry","src_ip":"203.0.113.12"}'
post '{"source":"cowrie","eventid":"cowrie.login.failed","username":"test","password":"test","src_ip":"203.0.113.13"}'
post '{"source":"opencanary","eventid":"canary.login.failed","username":"guest","password":"guest","src_ip":"203.0.113.14"}'
echo " done"
