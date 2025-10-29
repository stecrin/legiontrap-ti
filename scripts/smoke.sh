#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8088}"
API_KEY="${API_KEY:-dev-123}"

echo "== Smoke against: $BASE =="
echo "-- GET /api/health"
curl -fsS "$BASE/api/health" | python -m json.tool

echo "-- GET /api/stats (auth ok)"
curl -fsS -H "x-api-key: ${API_KEY}" "$BASE/api/stats" | python -m json.tool

echo "-- GET /api/iocs/ufw.txt (first lines)"
curl -fsS -H "x-api-key: ${API_KEY}" "$BASE/api/iocs/ufw.txt" | sed -n '1,20p'

echo "-- NEGATIVE: wrong key → expect 401"
code=$(curl -s -o /dev/null -w '%{http_code}' -H "x-api-key: BADKEY" "$BASE/api/stats")
if [[ "$code" == "401" ]]; then
  echo "✓ got 401 as expected"
else
  echo "✗ expected 401, got $code"
  exit 1
fi

echo "All smoke checks passed."
