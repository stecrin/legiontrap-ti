# PROJECT SUMMARY — LegionTrap TI

_Last updated: 2026-05-30 by Claude (onboarding run)_

## What it is
LegionTrap TI is a self-hosted behavioral threat intelligence platform for honeypot operators. It ingests attack events from a local sensor, builds behavioral fingerprints across five dimensions (timing, sequence, protocol, credential, target), clusters fingerprints into campaigns using a deterministic similarity algorithm, tracks longitudinal fingerprint history, and provides an optional AI-assisted reasoning layer for natural-language threat analysis. All storage is local (SQLite). No cloud dependency is required.

## Why it exists
Indicator-based threat intel (IPs, domains, hashes) decays fast because infrastructure is cheap to rotate. Behavioral patterns change slowly. LegionTrap bets on behavioral, longitudinal intelligence as the durable category — a fingerprint built over months survives infrastructure rotation that would expire any indicator. The operator owns the data entirely.

## Current release
v0.34.0 — Phase 7 (Actor Intelligence) complete. All planned phases from Phase 0 to Phase 7 shipped.

## Architecture in one paragraph
Two structurally isolated paths: (1) **ingest path** — events → GeoIP enrichment → fingerprint update → campaign clustering (deterministic, runs on every ingest); (2) **reasoning path** — AI analysis on operator request (read-only, never writes to campaign/fingerprint/actor tables). Backend: FastAPI (Python 3.11) + SQLAlchemy + Alembic (SQLite/PostgreSQL-compatible). Frontend: React 19 + Vite + TypeScript dashboard. Auth: JWT + API key + bcrypt. Rate limiting: slowapi.

## Stack
| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| API framework | FastAPI + uvicorn |
| ORM / migrations | SQLAlchemy + Alembic (15 migrations) |
| Storage | SQLite (WAL mode) — default: `storage/legiontrap.db` |
| Auth | JWT (python-jose) + API key + bcrypt (passlib) |
| Rate limiting | slowapi |
| GeoIP | geoip2 + MaxMind GeoLite2 (`storage/GeoLite2-City.mmdb`) |
| AI backends | Claude API or Ollama (optional, default: none) |
| Frontend | React 19, TypeScript, Vite, Recharts (`ui/dashboard/`) |
| Container | Docker + Docker Compose (`docker/docker-compose.edge.yml`) |
| CI/CD | GitHub Actions (lint → test → pip-audit → bandit → semantic-release) |
| Formatter | black (100 chars, py311) + ruff (E,F,I,B,UP,SIM) + isort |
| Test runner | pytest (unit / integration / db tiers) |

## Entry points
- **API server:** `app/main.py` → `uvicorn app.main:app --port 8088`
- **Frontend dev:** `ui/dashboard/` → `npm run dev` (Vite :5173)
- **Docker:** `docker/docker-compose.edge.yml`

## Key commands
| Action | Command |
|---|---|
| Install | `pip install -r requirements.txt` |
| Run API | `make run` |
| Dev mode (fastapi) | `make ui` |
| Test | `pytest -q` |
| Test with coverage | `pytest -q --cov=app` |
| Lint | `black --check . && ruff check .` |
| Format (fix) | `black . && ruff check --fix .` |
| Security audit | `pip-audit` + `bandit -r app/ -ll` |
| DB migrate | `make db-migrate` |
| DB status | `make db-status` |
| Smoke test | `make smoke` |

## Test structure
```
tests/
  unit/         26 files — fingerprinting, similarity, AI, stability, actor logic
  integration/  26 files — endpoint tests (FastAPI TestClient)
  db/           10 files — repository layer tests
  conftest.py   — shared fixtures
  test_*.py     — additional root-level tests (auth, iocs, privacy)
```
Tests run against in-memory SQLite (`DB_PATH=:memory:` via pytest.ini).

## Phase history
| Phase | Topic | Status |
|---|---|---|
| 0 | Security & Infra Hygiene | ✅ |
| 1 | SQLite Storage Foundation | ✅ |
| 2 | HTTP Ingestion API | ✅ |
| 3 | GeoIP Enrichment & IOC Exports | ✅ |
| 4 | Campaign Intelligence & Export Maturity | ✅ |
| 5 | AI Integration | ✅ |
| 6 | Async AI, Output Persistence & Brief UI | ✅ |
| 7 | Actor Intelligence | ✅ |
| 8 | Behavioral Federation | ○ conditional |

## Do-not-touch zones
- `storage/legiontrap.db` — live SQLite database with real sensor data
- `storage/events*.jsonl` — real event logs
- `storage/GeoLite2-City.mmdb` — MaxMind binary, not regenerable from source
- `.env` — secrets (not committed)
- `app/db/migrations/` — Alembic migration history; never edit existing files
