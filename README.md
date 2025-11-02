# LegionTrap TI

![CI](https://github.com/stecrin/legiontrap-ti/actions/workflows/ci.yml/badge.svg)
![Release](https://img.shields.io/github/v/release/stecrin/legiontrap-ti?label=release)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Tests](https://github.com/stecrin/legiontrap-ti/actions/workflows/ci.yml/badge.svg)


Modular, edge-ready honeynet with privacy-by-design, ATT&CK/Sigma exports, and a clean UI.

## Status

Initializing repository skeleton (Step 1).

---

## Quick start (local)

```bash
# build & start (Docker compose + API)
make up

# health (open route, no auth)
curl -s http://127.0.0.1:8088/api/health | python -m json.tool

# protected routes (require x-api-key)
H='x-api-key: dev-123'
curl -s -H "$H" http://127.0.0.1:8088/api/config | python -m json.tool
curl -s -H "$H" http://127.0.0.1:8088/api/stats  | python -m json.tool
curl -s -H "$H" http://127.0.0.1:8088/api/iocs/ufw.txt
curl -s -H "$H" http://127.0.0.1:8088/api/iocs/pf.conf
```

---

## Tests: IOC Exports

```bash
# Run isolated tests for IOC export logic
make test-iocs
```

This verifies that the IOC export endpoints function as expected:

* **/api/iocs/pf.conf** correctly reads attacker IPs from the configured `EVENTS_FILE`
* IPs are output in valid `pf.conf` syntax (`table <blocked_ips>` etc.)
* API key protection works via the environment variable `API_KEY=dev-123`
* Test suite writes a temporary JSONL file and ensures IOC generation works end-to-end

The IOC test target can be executed independently:

```bash
make test-iocs
```

If the app is running in a clean environment, this will automatically:

1. Set `PYTHONPATH` and `API_KEY`
2. Run `pytest -v tests/test_iocs.py`
3. Display pass/fail results in detailed mode


---

## Smoke test (IOC export)

This quick check proves the `/api/iocs/pf.conf` endpoint reads attacker IPs from your events file and enforces API key auth.

```bash
# 1) Create a tiny sample events file
printf '%s\n' '{"src_ip":"8.8.8.8"}' '{"data":{"src_ip":"1.1.1.1"}}' > /tmp/events.jsonl

# 2) Run the UI backend against that file
EVENTS_FILE=/tmp/events.jsonl API_KEY=dev-123 PRIVACY_MODE=off \
uvicorn ui.backend.app.main:app --port 8088 --no-server-header --no-access-log & pid=$!

# 3) Fetch pf.conf (authorized)
sleep 1
curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/iocs/pf.conf
# -> table <blocked_ips> persist { 1.1.1.1, 8.8.8.8 }
#    block in quick from <blocked_ips> to any

# 4) Negative-key test (should be 401)
curl -i -s -H 'x-api-key: WRONG' http://127.0.0.1:8088/api/iocs/pf.conf | head -5

# 5) Clean up the server
kill "$pid" >/dev/null 2>&1 || true
```

### Privacy mode (masking)

If you need to distribute IOCs without exposing full IPs, set `PRIVACY_MODE=on`. The last octet is masked:

```bash
EVENTS_FILE=/tmp/events.jsonl API_KEY=dev-123 PRIVACY_MODE=on \
uvicorn ui.backend.app.main:app --port 8088 --no-server-header --no-access-log & pid=$!
sleep 1
curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/iocs/pf.conf
# -> table <blocked_ips> persist { 1.1.1.x, 8.8.8.x }
kill "$pid" >/dev/null 2>&1 || true
```

---

## Authentication

All non-health endpoints require the `x-api-key` header.
In local compose we set `API_KEY=dev-123` (see `docker/docker-compose.edge.yml`). Change it for your environment.

**Negative test (bad key → 401)**

```bash
curl -i -H 'x-api-key: wrong-key' http://127.0.0.1:8088/api/stats
# Expect: HTTP/1.1 401 Unauthorized
```

---

## Privacy mode

Set `PRIVACY_MODE=on` to redact/limit personally identifying fields during normalization & exports (e.g., mask last IPv4 octet).

Check current runtime config:

```bash
H='x-api-key: dev-123'
curl -s -H "$H" http://127.0.0.1:8088/api/config | python -m json.tool
```

Example effect on IOC exports:

* `PRIVACY_MODE=off` → `8.8.8.8`
* `PRIVACY_MODE=on`  → `8.8.8.x`

---

## Environment configuration

| Variable           | Default              | Description                                                                 |
| ------------------ | -------------------- | --------------------------------------------------------------------------- |
| `API_KEY`          | `dev-123`            | Required header for protected endpoints (`x-api-key`).                      |
| `PRIVACY_MODE`     | `on`                 | If `on`, masks last IPv4 octet in IOC outputs & redacts PII where relevant. |
| `EVENTS_FILE`      | —                    | **Preferred.** Absolute path to events JSONL (overrides `EVENTS_PATH`).     |
| `EVENTS_PATH`      | `/data/events.jsonl` | Secondary path used if `EVENTS_FILE` is not set.                            |
| `ROTATE_MAX_BYTES` | `1000000`            | Max size in bytes before log rotation of `events.jsonl`.                    |
| `RETENTION_DAYS`   | `14`                 | Days to keep rotated event files.                                           |

**Precedence:**
The API resolves the events file as:
`EVENTS_FILE → EVENTS_PATH → storage/events.jsonl`.

---

## Seed demo data

Populate the API with a few example failed-logins so you can test charts/exports:

```bash
make seed

# verify:
curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/stats | python -m json.tool
curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/iocs/ufw.txt
curl -s -H 'x-api-key: dev-123' http://127.0.0.1:8088/api/iocs/pf.conf
```

---

## IOC exports

* **UFW (deny list):**

  ```bash
  H='x-api-key: dev-123'
  curl -s -H "$H" http://127.0.0.1:8088/api/iocs/ufw.txt | sed -n '1,50p'
  ```

  Example lines (privacy off):

  ```
  deny from 203.0.113.10
  deny from 8.8.8.8
  ```

  Example lines (privacy on):

  ```
  deny from 203.0.113.x
  deny from 8.8.8.x
  ```

* **pf.conf (FreeBSD/macOS PF table):**

  ```bash
  H='x-api-key: dev-123'
  curl -s -H "$H" http://127.0.0.1:8088/api/iocs/pf.conf | sed -n '1,50p'
  ```

  Example (privacy off):

  ```
  table <blocked_ips> persist { 203.0.113.10, 8.8.8.8 }
  block in quick from <blocked_ips> to any
  ```

---

## Events paging & time filter

Fetch events in pages and/or only after a given timestamp.

* `limit` — max events to return (default 50)
* `after_ts` — ISO8601 timestamp; returns events strictly after this time

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

---

## API reference (MVP)

* `GET /api/health` — liveness probe (no auth).
* `GET /api/config` — current effective config (auth).
* `GET /api/stats` — aggregate counts by time/source/type (auth).
* `GET /api/events` — all events (auth; may be large).
* `GET /api/events/paged?limit=&after_ts=` — paginated/time-filtered (auth).
* `GET /api/iocs/ufw.txt` — UFW deny rules (auth).
* `GET /api/iocs/pf.conf` — PF table & block rule (auth).
* `POST /api/ingest` — normalize + append single event (auth; JSON body).
* `POST /api/events` — append normalized event (auth; JSON body).

**Example ingest:**

```bash
H='x-api-key: dev-123'
curl -s -H "$H" -H 'Content-Type: application/json' \
  -d '{"source":"cowrie","type":"auth_failed","data":{"username":"root","password":"test","ip":"203.0.113.99"}}' \
  http://127.0.0.1:8088/api/ingest | python -m json.tool
```

---

## 🔎 Quick smoke test (local)

With the API running locally (default: `http://127.0.0.1:8088`) you can verify core routes:

```bash
# open route
curl -fsS http://127.0.0.1:8088/api/health | python -m json.tool

# protected routes (require x-api-key)
H='x-api-key: dev-123'
curl -fsS -H "$H" http://127.0.0.1:8088/api/stats | python -m json.tool
curl -fsS -H "$H" http://127.0.0.1:8088/api/iocs/ufw.txt | sed -n '1,20p'
curl -fsS -H "$H" http://127.0.0.1:8088/api/iocs/pf.conf | sed -n '1,20p'

# Negative-key check (should be 401)
curl -s -o /dev/null -w '%{http_code}\n' -H 'x-api-key: BADKEY' http://127.0.0.1:8088/api/stats
```

---

## Helpful make targets

```text
make up       # build & start API
make smoke    # run end-to-end test
make seed     # populate demo data
make logs     # follow API logs
make down     # stop containers
```

---

## Troubleshooting

* **Accidentally pasted README text into your shell**
  That runs non-commands like headings. Always paste *only* terminal commands (like above), not Markdown.

* **401 Unauthorized**
  Ensure you pass `x-api-key` and that `API_KEY` is set in compose/env.

* **Port already in use**
  Free 8088 or change the port in compose and `make up` again.

* **No IOC output**
  Confirm events path (see precedence), that events contain public IPv4s, and run `make seed`.

* **Events file path confusion**
  Remember precedence: `EVENTS_FILE` overrides `EVENTS_PATH`, otherwise `storage/events.jsonl` is used.

---

## Contributing

PRs welcome. Please run linters and tests locally before pushing:

```bash
ruff check --fix .
black .
isort .
pytest -q
```

### Git workflow

```bash
git add app/routers/iocs_pf.py Makefile README.md
git commit -m "Docs: enhance README; add IOC examples; clarify EVENTS_FILE precedence; expand API reference"
```

---

## License

Licensed under the **MIT License** © 2025 **Stefan Cringusi**.
See the full text in [`LICENSE`](LICENSE).

**SPDX-License-Identifier:** MIT

> If this project includes third-party libraries or assets, their licenses are documented in `THIRD_PARTY_NOTICES.md`.

# force rebuild
