# LegionTrap TI

## Table of Contents
- [Vision](#-vision)
- [Roadmap](#-roadmap)
- [Tech Stack](#-tech-stack)
- [Architecture Overview](#-architecture-overview)
- [Quick Start](#quick-start-local)
- [API Endpoints](#api-endpoints)
- [Database Operations](#database-operations)
- [Environment Configuration](#environment-configuration)
- [Privacy & Anonymization](#privacy--anonymization)
- [Tests & CI](#tests--ci)
- [Troubleshooting](#troubleshooting)
- [Release Automation](#-release-automation)
- [Contributing](#contributing)
- [License](#license)


## 🚀 Roadmap

| Phase | Focus Area | Status |
|-------|-------------|--------|
| **Phase 0** | Security & Infrastructure Hygiene | ✅ Complete |
| **Phase 1** | SQLite Storage Foundation | ✅ Complete |
| **Phase 2** | HTTP Ingestion API | ✅ Complete |
| **Phase 3** | GeoIP Enrichment | ⏳ Next |
| **Phase 4** | ATT&CK Mapping & Standard Exports | ⏳ Planned |
| **Phase 5** | AI Integration | ⏳ Planned |
| **Phase 6** | Behavioral Memory & Campaign Tracking | ⏳ Planned |
| **Phase 7** | Privacy-Preserving Federation | ⏳ Planned |

Each phase builds on the previous. See [docs/ROADMAP.md](docs/ROADMAP.md) for full detail.

---

## 💡 Vision

LegionTrap TI was born from a simple idea: to turn raw hacker noise into real, understandable insight.
It's not just another honeypot... it's a living system that listens, learns, and reacts.
Every IP that touches your network leaves a trace, and LegionTrap TI captures it, cleans it, and turns it into something you can actually use.

The goal is independence.
You don't need a massive enterprise setup or cloud subscription to understand who's targeting you; you can host your own private threat-intelligence environment, built with open tools and transparent logic.
Step by step, LegionTrap TI is evolving into a smart, self-sustaining platform that detects, analyzes, and reports attacks in real time, helping you stay one step ahead without relying on anyone else's system.

*Pleased to stand among those securing humanity's future in the digital age.
Every small defense matters in securing humanity's future.*

**— Stefan Cringusi**


## 🧠 Tech Stack

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Framework-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-2088FF?logo=githubactions&logoColor=white)
![Semantic Release](https://img.shields.io/badge/Semantic%20Release-Automated%20Versioning-blueviolet?logo=semanticrelease&logoColor=white)
![MIT License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 🏗️ Architecture Overview

Events arrive via `POST /api/ingest`, are validated and normalized, and are stored in SQLite. All dashboard and IOC queries run SQL via `EventRepository`. A JSONL file is maintained as a best-effort append-only replica.

```
Honeypot sensors (Cowrie, Dionaea, ...)
         │
         │  POST /api/ingest  (x-api-key)
         ▼
    FastAPI Backend (app/)
         │  Pydantic validation → normalization → deduplication
         ▼
    storage/legiontrap.db  (SQLite, primary store)
         │  INSERT raw_events + events + UPSERT source_ips
         │  INSERT audit_log
         │
         │  best-effort replica
         ▼
    storage/events.jsonl

    Read path: SQL queries via EventRepository
         │
         ▼
    GET /api/stats, /api/events, /api/iocs/pf.conf, /api/iocs/ufw.txt
         │
         ▼
    Browser dashboard / firewall scripts
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full component map.

---

## Quick Start (local)

```bash
# 1. Copy and populate required environment variables
cp .env.example .env
# Edit .env: set API_KEY, FEED_SALT, DASH_USER, DASH_PASS (bcrypt hash)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply database migrations
make db-migrate

# 4. Start the API
make run

# 5. Health check
curl -s http://127.0.0.1:8088/api/health | python -m json.tool

# 6. Ingest a test event
H='x-api-key: <your-API_KEY>'
curl -s -H "$H" -H 'Content-Type: application/json' \
  -d '{"events":[{"ts":"2025-10-28T18:31:08+00:00","source":"cowrie","type":"cowrie.login.failed","data":{"ip":"1.2.3.4","username":"root","password":"bad"}}]}' \
  http://127.0.0.1:8088/api/ingest | python -m json.tool

# 7. Stats and IOC exports
curl -s -H "$H" http://127.0.0.1:8088/api/stats | python -m json.tool
curl -s -H "$H" http://127.0.0.1:8088/api/iocs/ufw.txt
curl -s -H "$H" http://127.0.0.1:8088/api/iocs/pf.conf
```

---

## API Endpoints

| Method | Path                    | Auth | Description                           |
|-------:|-------------------------|:----:|---------------------------------------|
| GET    | `/api/health`           |  No  | Liveness check                        |
| POST   | `/api/login`            |  No  | Dashboard login → JWT token           |
| POST   | `/api/ingest`           | API key | Batch event ingest (up to 500)     |
| GET    | `/api/stats`            | Yes  | Total events, unique IPs, last-24h    |
| GET    | `/api/events`           | Yes  | Recent events (newest first)          |
| GET    | `/api/iocs/ufw.txt`     | Yes  | UFW deny list (privacy-aware)         |
| GET    | `/api/iocs/pf.conf`     | Yes  | PF table config (privacy-aware)       |

**Auth options:**
- API key header: `x-api-key: <API_KEY>`
- JWT bearer (dashboard): `Authorization: Bearer <token>`

---

## Database Operations

```bash
# Apply all pending migrations (run once after first deploy and after each new migration)
make db-migrate

# Check current migration revision
make db-status

# Show migration history
make db-pending

# Roll back one migration step (use with caution)
make db-rollback

# Prune events older than a cutoff date
make db-prune PRUNE_BEFORE=2025-01-01T00:00:00+00:00

# Import existing JSONL data
make import-jsonl JSONL_FILES="storage/events.jsonl"

# Verify migration correctness (tables, indexes, revision)
make db-validate
```

---

## Environment Configuration

| Variable           | Required | Description                                                      |
| ------------------ | :------: | ---------------------------------------------------------------- |
| `API_KEY`          | Yes      | Required header for protected endpoints (`x-api-key`).          |
| `FEED_SALT`        | Yes      | HMAC salt for privacy-mode IP hashing.                           |
| `DASH_USER`        | Yes      | Dashboard login username.                                        |
| `DASH_PASS`        | Yes      | Dashboard password as a bcrypt hash.                             |
| `PRIVACY_MODE`     | No       | Set `on` to enable privacy masking on IOC exports (default off). |
| `CORS_ORIGINS`     | No       | Comma-separated allowed origins (default: localhost variants).   |
| `DB_PATH`          | No       | SQLite file path (default: `storage/legiontrap.db`).             |
| `LOGIN_RATE_LIMIT` | No       | Rate limit for `/api/login` (default: `5/minute`).               |
| `EVENTS_FILE`      | No       | JSONL replica path (default: `storage/events.jsonl`). Deprecated; kept for recovery use. |

Copy `.env.example` for a template with all required variables.

---

## Privacy & Anonymization

IOC exports support two privacy strategies controlled by `PRIVACY_MODE` and `FEED_SALT`:

**`PRIVACY_MODE=off`** (default): Full IPs exported as-is.
```
8.8.8.8
```

**`PRIVACY_MODE=on`, no `FEED_SALT`**: Last octet masked.
```
8.8.8.x
```

**`PRIVACY_MODE=on`, `FEED_SALT` set**: Deterministic HMAC token (same IP + salt = same token).
```
ip-a3b4c5d6e7f8
```

Private, loopback, link-local, and reserved IPs are always filtered from exports regardless of privacy mode.

---

## Tests & CI

```bash
# Full test suite
pytest -q

# With coverage
pytest -q --cov=app

# Lint checks (must pass before commit)
black --check .
ruff check .
```

CI runs on every push and PR: lint → tests → `pip-audit` → `bandit`. See `.github/workflows/ci.yml`.

---

## Troubleshooting

**`401 Unauthorized`**
Set the `x-api-key` header matching `API_KEY` in your `.env`.

**Empty IOC output**
Ingest at least one event with a routable public IP via `POST /api/ingest`. Private IPs (`RFC1918`, loopback, link-local) are stored as `src_ip=NULL` and never appear in exports.

**Database not found / no tables**
Run `make db-migrate` to create the schema. The application does not auto-migrate on startup.

**Port already in use**
Free port 8088 or set `PORT=<other>` when calling `make run`.

---

## 🚀 Release Automation

This repository uses **semantic-release** to automatically handle versioning, tagging, and changelog updates.

Each time a commit is pushed to `main`:

1. GitHub Actions runs the **Auto Version & Release** workflow.
2. Based on commit messages, it determines the correct semantic version bump.
3. It generates or updates `CHANGELOG.md`.
4. It creates and publishes a new GitHub Release.

### Conventional Commit Examples

| Commit type | Example                             | Effect                    |
| ----------- | ----------------------------------- | ------------------------- |
| **fix:**    | `fix: resolve missing IOC export`   | Patch release (x.x.+1)   |
| **feat:**   | `feat: add new dashboard API route` | Minor release (x.+1.0)   |
| **perf!:**  | `perf!: refactor ingestion engine`  | Major release (+1.0.0)   |

---

## Contributing

PRs welcome. Run linters and tests locally before pushing:

```bash
ruff check --fix .
black .
pytest -q
```

---

## 🧾 Changelog & Release History

[![GitHub release](https://img.shields.io/github/v/release/stecrin/legiontrap-ti?label=Current%20Version&color=blue)](https://github.com/stecrin/legiontrap-ti/releases/latest)

[View CHANGELOG.md →](https://github.com/stecrin/legiontrap-ti/blob/main/CHANGELOG.md)

---

## License

Licensed under the **MIT License** © 2025 **Stefan Cringusi**.
See the full text in [`LICENSE`](LICENSE).

**SPDX-License-Identifier:** MIT
