# LegionTrap TI

## Table of Contents
- [Thesis](#thesis)
- [What This Is](#what-this-is)
- [The Intelligence Model](#the-intelligence-model)
- [Architecture Overview](#architecture-overview)
- [Sovereignty Model](#sovereignty-model)
- [Current State](#current-state)
- [Direction](#direction)
- [Roadmap](#roadmap)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start-local)
- [API Reference](#api-reference)
- [Database Operations](#database-operations)
- [Environment Configuration](#environment-configuration)
- [Privacy & Anonymization](#privacy--anonymization)
- [Tests & CI](#tests--ci)
- [Troubleshooting](#troubleshooting)
- [Release Automation](#release-automation)
- [Contributing](#contributing)
- [License](#license)


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

## Architecture Overview

The system has two structurally isolated paths. The ingest path runs on every event; the reasoning path runs on operator request. The ingest path imports nothing from the AI layer. The reasoning path never writes to campaign, fingerprint, or event tables. Removing the reasoning path leaves the ingest path fully functional.

```
External sensors
       │
       ▼
  Ingest + GeoIP enrichment
       │
       ▼
  Behavioral fingerprinting  (5 dimensions)
       │
       ▼
  Campaign clustering  (deterministic similarity scoring)
       │
       ├─→  Fingerprint history
       └─→  Behavioral stability
                    │
            [on operator request]
                    ▼
           AI reasoning layer  (read-only)
                    │
                    ▼
          Operator review and decision
```

The ingest path receives event batches, validates and normalizes them, enriches with GeoIP data, and writes to the local database. After each ingest, behavioral fingerprints are updated for affected source IPs and campaign clustering runs: each fingerprint is compared against all active campaign fingerprints, and a deterministic decision is recorded — automatic association, uncertain association, or new campaign — along with per-dimension similarity scores.

Campaign records accumulate observations across multiple IPs and across time. Every fingerprint recompute appends a snapshot to that source's history. Behavioral stability is derived from that history: pairwise similarity between consecutive snapshots produces a per-dimension stability score. High stability indicates consistent behavior; declining stability across recent snapshots may indicate tooling or operational adaptation.

On operator request, the AI reasoning layer reads from campaign records, fingerprints, and stability scores and produces a natural-language summary or threat brief. The endpoint returns a job ID immediately; the analysis runs in the background. AI outputs are stored immutably alongside their data sources, prompt hash, and safety validation results. The AI audit log records metadata only — operation type, byte counts, latency — without storing content.

Uncertain clustering associations are surfaced for analyst review. A review decision is recorded on the observation without altering the original clustering outcome or campaign membership. Actor attribution will be operator-assigned. No automatic action is taken anywhere in the system.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full component map, repository structure, and API contract details.

---

## Sovereignty Model

The behavioral fingerprints LegionTrap builds are specific to one operator's exposure profile: their services, their network, their attack surface. Local storage is not primarily a privacy measure — it is a requirement for the intelligence to be relevant. Your attack history can only be built from your observations. A service that does not have access to your sensor data cannot build your behavioral memory for you.

Commercial threat feeds provide intelligence derived from external, aggregated observations. That intelligence is useful for blocking known-bad infrastructure. It is not useful for understanding whether a behavioral pattern targeting your specific services has appeared before, or whether a dormant campaign has returned. No feed can provide that answer because no feed has your longitudinal record.

PRIVACY_MODE addresses a specific operational need: IOC exports — firewall block lists, deny rules — are often shared across teams or integrated into partner systems. An operator may need to publish actionable block rules without revealing the specific IPs they have observed. PRIVACY_MODE separates the intelligence asset from the operational artifact. The two can be managed independently.

The clustering algorithm, fingerprint builder, and stability scorer are deterministic: the same inputs always produce the same output. This is an operational requirement. An operator who needs to understand why a source was assigned to a campaign can read the per-dimension similarity scores stored with every observation. Explainability is not a layer added on top of the intelligence pipeline — it is part of the core data model.

The AI reasoning layer is disabled by default. When enabled, it supports fully local inference; a cloud backend is an operator configuration choice, not a dependency. Every AI request is logged with metadata — operation type, byte counts, latency — without storing prompt content or response text. Every AI output is stored immutably with its data sources and safety validation results. The audit trail answers the operational question "what analysis was performed and on what data" without reconstructing the analysis.

No decision in LegionTrap is made automatically. Campaign membership is computed deterministically; uncertain cases are surfaced for operator review. AI analysis is generated on request; it does not trigger action. The operator is not a step in an automated pipeline. The operator is the decision layer.

---

## Current State

Through Phase 6, LegionTrap supports the complete behavioral intelligence pipeline: event ingestion, behavioral fingerprinting, campaign clustering, longitudinal fingerprint history, behavioral stability scoring, and AI-assisted reasoning on operator request. An operator with a Phase 6 deployment can ingest adversarial traffic from their sensors, build behavioral fingerprints per source IP, track campaigns as they accumulate observations across multiple IPs over time, and request natural-language analysis of any campaign or time-bounded event set.

The intelligence pipeline from ingest to campaign assignment is deterministic and requires no AI backend. Behavioral fingerprints build automatically on each ingest cycle. Campaigns transition through lifecycle states — active, dormant, historical — on configurable time thresholds. Uncertain clustering associations are surfaced as a review queue; the operator confirms or denies each one. The full path produces no external API calls and generates no output until the operator requests it.

The AI reasoning layer, when configured, does not alter the deterministic outputs. Campaign similarity scores, fingerprint confidence values, and behavioral stability metrics are produced by algorithms that are unaffected by the AI configuration. What AI adds is natural-language interpretation on demand: a summary that translates a confidence score and reactivation count into a paragraph an analyst can read, or a multi-campaign brief filtered to a specific time window. Every output is stored immutably alongside its data sources, prompt hash, and safety validation results. The AI layer never writes to campaign or fingerprint tables.

Known limitations: the actor identity schema is present but has no attribution logic — `actor_profiles` and `campaign_lineage` exist with full repository support, but no API endpoints expose them and no automatic assignment runs. Fingerprint history is being collected but no drift-threshold alerting exists. Analyst review decisions on uncertain associations are stored but not yet used to influence similarity thresholds.

---

## Direction

Phase 7 addresses two architectural problems that Phase 6 prepared for. The first is actor identity: campaigns currently represent coordinated activity without linking to an explicit actor record. Phase 7 introduces operator-assigned actor profiles, connecting campaigns to inferred actor identities through explicit relationship types and confidence values. Attribution is always operator-confirmed; no automated assignment is planned. The Phase 6 foundations — `actor_profiles` and `campaign_lineage` schema, `ActorRepository` — are the prepared substrate for this work.

The second problem is the boundary of the behavioral record. A single deployment's fingerprint history is specific to its own attack surface, which is both its strength and its limit. An actor targeting multiple operators will be independently discovered by each one. Federation is the mechanism for sharing behavioral patterns across deployments without sharing the observation data those patterns were derived from. A fingerprint encodes behavioral characteristics — timing distributions, probe sequences, protocol behavior — not IP addresses. The pattern can be shared without sharing the source.

Privacy-preserving behavioral federation is the logical continuation of the thesis: if behavioral patterns are more durable than indicators, then a network of operators sharing behavioral patterns gains intelligence that no individual deployment can produce alone. A campaign fingerprint observed for the first time in one deployment may match a fingerprint another operator has been tracking for months. The match is made without either operator revealing their observation infrastructure to the other. No timelines. The foundation is built.

---

## Roadmap

| Phase | Focus Area | Status |
|-------|-------------|--------|
| **Phase 0** | Security & Infrastructure Hygiene | ✅ Complete |
| **Phase 1** | SQLite Storage Foundation | ✅ Complete |
| **Phase 2** | HTTP Ingestion API | ✅ Complete |
| **Phase 3** | GeoIP Enrichment & Intelligence Exports | ✅ Complete |
| **Phase 4** | Campaign Intelligence & Export Maturity | ✅ Complete |
| **Phase 5** | AI Integration | ✅ Complete |
| **Phase 6** | Async AI, Output Persistence & Brief UI | ✅ Complete |
| **Phase 7** | Actor Identity and Behavioral Federation | ⏳ Next |

Each phase builds on the previous. See [docs/ROADMAP.md](docs/ROADMAP.md) for full detail.

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Framework-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?logo=docker&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-2088FF?logo=githubactions&logoColor=white)
![Semantic Release](https://img.shields.io/badge/Semantic%20Release-Automated%20Versioning-blueviolet?logo=semanticrelease&logoColor=white)
![MIT License](https://img.shields.io/badge/License-MIT-green.svg)

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

## API Reference

The complete API endpoint reference, authentication model, and contract details are documented in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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

## Release Automation

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

## Changelog & Release History

[![GitHub release](https://img.shields.io/github/v/release/stecrin/legiontrap-ti?label=Current%20Version&color=blue)](https://github.com/stecrin/legiontrap-ti/releases/latest)

[View CHANGELOG.md →](https://github.com/stecrin/legiontrap-ti/blob/main/CHANGELOG.md)

---

## License

Licensed under the **MIT License** © 2025 **Stefan Cringusi**.
See the full text in [`LICENSE`](LICENSE).

**SPDX-License-Identifier:** MIT
