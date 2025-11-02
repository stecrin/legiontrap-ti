# LegionTrap TI

## 🚀 Roadmap & Future Features

LegionTrap TI is evolving into a **complete Threat Intelligence and Honeynet platform**, built for security professionals, researchers, and educators.

| Phase | Focus Area | Key Deliverables | Status |
|-------|-------------|------------------|--------|
| **Phase 1** | 🧩 Core API + IOC Exports | FastAPI backend, privacy masking, IOC generation, local seed data | ✅ Completed |
| **Phase 2** | ⚙️ CI/CD Automation | Semantic Release, GitHub Actions, changelog automation, version badges | ✅ Completed |
| **Phase 3** | 📊 Dashboard UI | Interactive React-based dashboard (FastAPI + Tailwind + Plotly) | 🔄 In progress |
| **Phase 4** | 🧠 Threat Intelligence Engine | Automatic enrichment (GeoIP, ASN, MITRE ATT&CK mapping) | ⏳ Planned |
| **Phase 5** | ☁️ Cloud & Edge Profiles | Cloud federation + distributed event collectors | ⏳ Planned |
| **Phase 6** | 🔔 Alerting & Integrations | Telegram & SIEM integration, webhooks, email alerts | ⏳ Planned |

Each phase builds upon the previous one — modular, reproducible, and secure by design.

---

**Educational-grade honeynet system** that teaches, detects, and defends.

---

## 💡 Vision

LegionTrap TI was born from a simple idea: to turn raw hacker noise into real, understandable insight.
It’s not just another honeypot... it’s a living system that listens, learns, and reacts.
Every IP that touches your network leaves a trace, and LegionTrap TI captures it, cleans it, and turns it into something you can actually use.

The goal is independence.
You don’t need a massive enterprise setup or cloud subscription to understand who’s targeting you; you can host your own private threat-intelligence environment, built with open tools and transparent logic.
Step by step, LegionTrap TI is evolving into a smart, self-sustaining platform that detects, analyzes, and reports attacks in real time, helping you stay one step ahead without relying on anyone else’s system.

*Pleased to stand among those securing humanity’s future in the digital age.
Every small defense matters in securing humanity’s future.*

**— Stefan Cringusi**


![CI](https://github.com/stecrin/legiontrap-ti/actions/workflows/ci.yml/badge.svg)
![Release](https://img.shields.io/github/v/release/stecrin/legiontrap-ti?label=release)
![Changelog](https://img.shields.io/badge/Changelog-Auto--Generated-blueviolet.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Tests](https://github.com/stecrin/legiontrap-ti/actions/workflows/ci.yml/badge.svg)

---

## 🧠 Tech Stack

Built with modern, modular, and production-grade technologies:

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Framework-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-2088FF?logo=githubactions&logoColor=white)
![Semantic Release](https://img.shields.io/badge/Semantic%20Release-Automated%20Versioning-blueviolet?logo=semanticrelease&logoColor=white)
![MIT License](https://img.shields.io/badge/License-MIT-green.svg)

The system is designed to be **secure, reproducible, and easy to extend**,
using containerized environments, reproducible builds, and automated release pipelines.

---

Modular, edge-ready honeynet with privacy-by-design, ATT&CK/Sigma exports, and a clean UI.

---

## 🏗️ Architecture Overview

🧠 **LegionTrap TI** is built around a modular, containerized architecture designed for clarity, privacy, and flexibility.

    ┌──────────────────────────────┐
    │          Frontend UI         │
    │   (Future dashboard / React) │
    └─────────────┬────────────────┘
                  │ REST API
    ┌─────────────┴────────────────┐
    │         FastAPI Backend      │
    │  - Event ingestion & parsing │
    │  - IOC export generation     │
    │  - Privacy masking & config  │
    └─────────────┬────────────────┘
                  │ JSONL Storage
    ┌─────────────┴────────────────┐
    │       Storage & Logging      │
    │  - Persistent JSONL events   │
    │  - Rotating logs / retention │
    └─────────────┬────────────────┘
                  │
    ┌─────────────┴────────────────┐
    │        Docker Compose        │
    │  - Edge deployment profile   │
    │  - Cloud profile (planned)   │
    └──────────────────────────────┘


🧩 **Key principles:**
- Minimal dependencies for reliability
- Reproducible, portable container setup
- Configurable privacy and export modes
- Modular paths for integration with honeypots and TI feeds
- Built for both **edge** and **cloud** environments

---


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

## 🚀 Release Automation

This repository uses **semantic-release** to automatically handle versioning, tagging, and changelog updates.

### How it works

Each time a commit is pushed to `main`:

1. GitHub Actions runs the **Auto Version & Release** workflow.
2. The workflow installs all semantic-release dependencies.
3. Based on your commit messages, it determines the correct semantic version bump.
4. It generates or updates the `CHANGELOG.md`.
5. It creates and publishes a new GitHub Release with tag and changelog notes.

### Conventional Commit Examples

| Commit type | Example                             | Effect                    |
| ----------- | ----------------------------------- | ------------------------- |
| **fix:**    | `fix: resolve missing IOC export`   | 🩹 Patch release (x.x.+1) |
| **feat:**   | `feat: add new dashboard API route` | 🚀 Minor release (x.+1.0) |
| **perf!:**  | `perf!: refactor ingestion engine`  | ⚡ Major release (+1.0.0)  |

### Manual Trigger

You can manually trigger a semantic release without changes:

```bash
git commit --allow-empty -m "chore(release): trigger semantic-release"
git push origin main
```

A new version will be created if the last commit didn’t already match the changelog.

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

* **Accidentally pasted README text into your shell** — only paste command sections.
* **401 Unauthorized** — ensure `x-api-key` matches your configured `API_KEY`.
* **Port already in use** — free 8088 or change port in compose.
* **No IOC output** — ensure valid events and correct `EVENTS_FILE`.
* **Events path confusion** — `EVENTS_FILE` overrides `EVENTS_PATH`, otherwise `storage/events.jsonl` is used.

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
