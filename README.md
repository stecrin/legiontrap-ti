# LegionTrap TI

## Table of Contents
- [Thesis](#thesis)
- [What This Is](#what-this-is)
- [The Intelligence Model](#the-intelligence-model)
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
| **Phase 3** | GeoIP Enrichment & Intelligence Exports | ✅ Complete |
| **Phase 4** | Campaign Intelligence & Export Maturity | ✅ Complete |
| **Phase 5** | AI Integration | ✅ Complete |
| **Phase 6** | Async AI, Output Persistence & Brief UI | ⏳ Next |
| **Phase 7** | Privacy-Preserving Federation | ⏳ Planned |

Each phase builds on the previous. See [docs/ROADMAP.md](docs/ROADMAP.md) for full detail.

---

## Thesis

Most threat intelligence is organized around indicators: IP addresses, domain names, file hashes, signatures. Each indicator represents a point-in-time observation of attacker infrastructure. The operational cycle becomes observe, publish, block. The useful life of that observation is bounded by how long the attacker continues to use that infrastructure. An IP is cheap to rotate. A domain costs a few dollars.

This has always been the structural limitation of indicator-based defense. What changes when AI tooling is widely available is the decay rate. Generating new domains, rotating infrastructure, and cycling credential lists become scripted tasks rather than manual ones. The cost of retiring a burned indicator approaches zero. The category of intelligence that gets cheapest to defeat is exactly the category most defensive tooling is organized to produce.

Behavioral patterns change more slowly. How an attacker conducts a campaign — their timing distributions, the sequence of probes, the credential preferences, the logic behind target selection — reflects operational decisions that are expensive to revise. These patterns persist across infrastructure rotation because they describe behavior, not addresses. A behavioral fingerprint built from months of observations survives changes that would expire any indicator. LegionTrap is built on the thesis that this kind of intelligence — longitudinal, behavioral, compounding — is worth the architectural complexity required to build it.

---

## What This Is

LegionTrap runs on a single operator's infrastructure, analyzing adversarial traffic from a sensor they control. The design is local-first: no shared intelligence feed, no cloud dependency. The system was built to process real events from a honeypot deployment running in an isolated network segment — actual scans, probes, and credential attempts from external adversarial activity.

The architecture follows from that operational context. Storage is local SQLite, compatible with PostgreSQL when scale requires migration. The AI reasoning layer supports fully local inference; cloud-based backends are available as an operator choice, not a dependency. PRIVACY_MODE is a first-class configuration option, not an afterthought. Every constraint in the design reflects the same underlying principle: the operator should own their intelligence entirely — not access to it through a subscription or a feed, but the data, the analysis pipeline, and the conclusions drawn from it.

---

## The Intelligence Model

LegionTrap does not treat events as isolated log entries. Each event contributes to a behavioral record for its source: a fingerprint that accumulates timing patterns, probe sequences, protocol behavior, credential choices, and target selection across all observed activity. The fingerprint is the unit of intelligence. The event is raw material.

A fingerprint is built across five dimensions. Timing captures inter-probe intervals and their distribution — the characteristic rhythm of specific tooling. Sequence captures the order in which ports and services are probed, which remains stable across infrastructure changes. Protocol captures behavior within sessions: authentication order, banner handling, handshake patterns. Credential captures the sets and strategies used in login attempts. Target captures which of the operator's services consistently attract attention. Each dimension is scored independently; a fingerprint is considered confident when multiple dimensions are populated and the event volume is sufficient.

Campaign clustering assigns fingerprints to campaigns using a weighted similarity algorithm. The algorithm is deterministic: the same fingerprint always produces the same result. A new fingerprint is compared against all active campaigns; if similarity exceeds a threshold, the source joins the existing campaign. If similarity is borderline, the association is flagged as uncertain and queued for analyst review. No machine learning is involved. The decision and its per-dimension similarity scores are stored with every observation, so the reasoning is always auditable.

Every time a fingerprint is recomputed, a snapshot is appended to that source's history. Over time this becomes longitudinal memory: a record of how observed behavior has changed, or not changed, across months of activity. A campaign that has been continuously observed for six months has a behavioral record that no feed purchase can replicate. The intelligence accumulates with time.

Behavioral stability measures how consistently a campaign has behaved across its fingerprint history. High stability indicates the campaign's tooling, timing, and targets have remained recognizable across all observed snapshots. Declining stability across recent snapshots may indicate adaptation. A sparse designation means the history is too short to compute meaningful stability metrics. Stability is a signal, not a verdict; the operator decides what a given stability profile means in their specific context.

The AI reasoning layer operates on this structured, deterministic data — fingerprints, campaign records, stability scores — and produces natural-language analysis on operator request. AI is not the source of the intelligence. It explains and contextualizes data that was produced entirely by deterministic algorithms. Every conclusion the AI layer draws is traceable to specific behavioral dimensions and similarity scores. The operator remains the final interpreter; no action is taken automatically.

---

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

Events arrive via `POST /api/ingest`, are validated and normalized, and are stored in SQLite. All dashboard and IOC queries run SQL via `EventRepository`.

```
Honeypot sensors (Cowrie, Dionaea, ...)
         │
         │  POST /api/ingest  (x-api-key)
         ▼
    FastAPI Backend (app/)
         │  Pydantic validation → normalization → deduplication
         │  GeoIP enrichment (country, city, ASN) via geoip2
         ▼
    storage/legiontrap.db  (SQLite, primary store)
         │  INSERT raw_events + events + UPSERT source_ips
         │  INSERT audit_log
         │
    Read path: SQL queries via EventRepository
         │
         ├── GET /api/stats, /api/events         → Browser dashboard
         ├── GET /api/iocs/pf.conf, /ufw.txt     → Firewall scripts
         ├── GET /api/intelligence/*             → Intelligence panels
         └── GET /api/exports/*                 → External TI tools
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

| Method | Path                              | Auth    | Description                              |
|-------:|-----------------------------------|:-------:|------------------------------------------|
| GET    | `/api/health`                     | No      | Liveness check                           |
| POST   | `/api/login`                      | No      | Dashboard login → JWT token              |
| POST   | `/api/ingest`                     | API key | Batch event ingest (up to 500)           |
| GET    | `/api/stats`                      | Yes     | Total events, unique IPs, last-24h       |
| GET    | `/api/events`                     | Yes     | Recent events (newest first)             |
| GET    | `/api/iocs/ufw.txt`               | Yes     | UFW deny list (privacy-aware)            |
| GET    | `/api/iocs/pf.conf`               | Yes     | PF table config (privacy-aware)          |
| GET    | `/api/intelligence/ips`           | Yes     | Top source IPs with reputation scores    |
| GET    | `/api/intelligence/ips/{ip}`      | Yes     | Detail record for a single IP            |
| GET    | `/api/intelligence/top-countries` | Yes     | Top countries by event count             |
| GET    | `/api/intelligence/top-asns`      | Yes     | Top ASNs by event count                  |
| GET    | `/api/exports/attack-navigator`   | Yes     | ATT&CK Navigator layer JSON              |
| GET    | `/api/exports/stix`               | Yes     | STIX 2.1 Indicator bundle (blocked when `PRIVACY_MODE=on`) |
| GET    | `/api/campaigns`                  | Yes     | Campaign list (paginated, sorted by last_seen DESC) |
| GET    | `/api/campaigns/{id}`             | Yes     | Campaign detail with members and observations |
| POST   | `/api/campaigns/{id}/summary`     | Yes     | AI-assisted campaign summary (operator-triggered) |
| POST   | `/api/campaigns/brief`            | Yes     | AI-assisted multi-campaign threat brief  |

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
| `PRIVACY_MODE`     | No       | Set `on` to enable privacy masking on IOC exports and block STIX export (default off). |
| `CORS_ORIGINS`     | No       | Comma-separated allowed origins (default: localhost variants).   |
| `DB_PATH`          | No       | SQLite file path (default: `storage/legiontrap.db`).             |
| `LOGIN_RATE_LIMIT` | No       | Rate limit for `/api/login` (default: `5/minute`).               |
| `AI_BACKEND`       | No       | AI inference backend: `none` (default), `claude`, or `ollama`.   |
| `ANTHROPIC_API_KEY`| No       | Required when `AI_BACKEND=claude`.                               |
| `AI_MODEL`         | No       | Model name override for Claude or Ollama (sensible defaults apply). |
| `OLLAMA_HOST`      | No       | Ollama API endpoint (default: `http://localhost:11434`).         |
| `AI_TIMEOUT_SECONDS` | No     | Timeout for AI backend requests in seconds (default: 30).        |

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
