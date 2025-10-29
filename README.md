# LegionTrap TI

![CI](https://github.com/stecrin/legiontrap-ti/actions/workflows/ci.yml/badge.svg)
![Release](https://img.shields.io/github/v/release/stecrin/legiontrap-ti?label=release)

Modular, edge-ready honeynet with privacy-by-design, ATT&CK/Sigma exports, and a clean UI.

## Status
Initializing repository skeleton (Step 1).

## Quick start (local)

    # start / rebuild (Docker compose + API)
    make up

    # health (open route, no auth)
    curl -s http://127.0.0.1:8088/api/health

    # protected routes (require x-api-key)
    H='x-api-key: dev-123'
    curl -s -H "$H" http://127.0.0.1:8088/api/config | python -m json.tool
    curl -s -H "$H" http://127.0.0.1:8088/api/stats  | python -m json.tool
    curl -s -H "$H" http://127.0.0.1:8088/api/iocs/ufw.txt
    curl -s -H "$H" http://127.0.0.1:8088/api/iocs/pf.conf

### Authentication
All non-health endpoints require the `x-api-key` header.
In local compose we set `API_KEY=dev-123` (see `docker/docker-compose.edge.yml`). Change it for your env.

### Negative test (bad key → 401)

    curl -i -H 'x-api-key: wrong-key' http://127.0.0.1:8088/api/stats
    # Expect: HTTP/1.1 401 Unauthorized

### Privacy mode
Set `PRIVACY_MODE=on` to redact/limit personally identifying fields during normalization/exports.

Check current runtime config:

    H='x-api-key: dev-123'
    curl -s -H "$H" http://127.0.0.1:8088/api/config | python -m json.tool

### Smoke test
Runs a quick end-to-end check: health, auth guard, ingest one event, stats delta, IOC outputs.

    make smoke

### Helpful make targets

    make up       # build & start API
    make smoke    # run end-to-end test
    make logs     # follow API logs
    make down     # stop containers

### Seed demo data
Populate the API with a few example failed-logins so you can test charts/exports:

    make seed
    # verify:
    curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/stats | python -m json.tool
    curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/iocs/ufw.txt
    curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/iocs/pf.conf

### Environment configuration
| Variable           | Default              | Description                                                        |
|--------------------|----------------------|--------------------------------------------------------------------|
| `API_KEY`          | `dev-123`            | Required header value for protected endpoints (`x-api-key`).       |
| `PRIVACY_MODE`     | `on`                 | If `on`, redacts/limits PII in normalized data & exports.          |
| `EVENTS_PATH`      | `/data/events.jsonl` | File path for JSON Lines event storage.                            |
| `ROTATE_MAX_BYTES` | `1000000`            | Max size in bytes before log rotation of `events.jsonl`.           |
| `RETENTION_DAYS`   | `14`                 | Days to keep rotated event files.                                  |
### Events paging & time filter

Fetch events in pages and/or only after a given timestamp.

- `limit` — max events to return (default 50).
- `after_ts` — ISO8601 timestamp; returns events strictly after this time.

Examples:

```bash
# First page (default limit)
curl -s -H 'x-api-key: dev-123' \
  'http://127.0.0.1:8088/api/events/paged' | python -m json.tool

# Small page size (e.g., 2)
curl -s -H 'x-api-key: dev-123' \
  'http://127.0.0.1:8088/api/events/paged?limit=2' | python -m json.tool

# Only events after a timestamp (UTC)
curl -s -H 'x-api-key: dev-123' \
  'http://127.0.0.1:8088/api/events/paged?after_ts=2025-01-01T00:00:00Z' | python -m json.tool

# Combine limit + after_ts
curl -s -H 'x-api-key: dev-123' \
  'http://127.0.0.1:8088/api/events/paged?limit=3&after_ts=2025-01-01T00:00:00Z' | python -m json.tool

```

## 🔎 Quick smoke test (local)

With the API running locally (default: `http://127.0.0.1:8088`) you can verify core routes:

```bash
# open route
curl -fsS http://127.0.0.1:8088/api/health | python -m json.tool

# protected routes (require x-api-key)
H='x-api-key: dev-123'
curl -fsS -H "$H" http://127.0.0.1:8088/api/stats | python -m json.tool
curl -fsS -H "$H" http://127.0.0.1:8088/api/iocs/ufw.txt | sed -n '1,20p'


Negative-key check (should be **401**):
```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'x-api-key: BADKEY' http://127.0.0.1:8088/api/stats
