# PROJECT STATUS — LegionTrap TI

_Last updated: 2026-06-12 (D2 closed)_

## Current phase
Post-Phase 7 / maintenance and hygiene hardening complete. Phase 7 (Actor Intelligence) is closed. Phase 8 (Behavioral Federation) is conditional on operational prerequisites (two willing pilot operators + validated fingerprint serialization format).

## Project priority
- **Level:** high
- **Reason:** Active development testing ground for autonomous Claude Code workflow; real sensor data in use; production-like local deployment.

## Production risk level
- **Level:** medium
- **Why:** Live SQLite database (`storage/legiontrap.db`) and real event JSONL files are present in the repo root. Not publicly deployed, but data is operational. 13 Alembic migrations are in place — schema changes carry rollback risk.

## Active branch
`main` (no active feature branch)

## AI authority level
`may-edit` — Claude may edit files on a feature branch, but must not commit, merge, or deploy without explicit human approval.

## Current Agile context
- **Current epic:** Testing infrastructure hardening
- **Current story:** C2 — COMPLETE; D2 — COMPLETE
- **Acceptance criteria:** C2: smoke-level API coverage running in CI via isolated in-memory SQLite — satisfied by `tests/unit/test_api_smoke.py` running under `pytest -q`. D2: `docs/LEGIONTRAP_EXPLAINED.md` accuracy confirmed against Phase 7 state — reviewed Stage 20A–20G, corrections merged in PR #90 (commit `cfa705d`), human sign-off granted 2026-06-12.
- **Backlog:** see `PROJECT_BACKLOG.md`

## Last completed task
2026-06-12 — D2 closed: `docs/LEGIONTRAP_EXPLAINED.md` reviewed against Phase 7 / Actor Intelligence state (Stage 20A), two editorial corrections applied and merged (PR #90, commits `cfa705d` / `5069b3a`), human sign-off granted. Prior: C2 closed 2026-06-11.

## Next task

* **Action:** Strategic backlog review — no further items in Epics A, C, or D remain open. Epics B1 and B2 are blocked on external prerequisites (two pilot operators). Next prioritisation decision is at Stefan's discretion.
* **Why it matters:** All active maintenance and documentation stories are closed. Proceeding requires a deliberate choice about what to work on next.
* **Done when:** Stefan selects the next priority and updates this file.
* **Owner:** Stefan.

## Commands / tests last run
- **Command:** `pytest -q`, `black --check .`, `ruff check .`, `bandit -r app/ -ll`, `pip-audit`
  **Result:** All pass (CI run 27349314838 on PR #87, 2026-06-11)
  **Date:** 2026-06-11
  **Notes:** 114 actor integration tests pass across all four actor test files. Bandit and pip-audit blocking gates remain clean.

## Known risks
- `storage/legiontrap.db` and `storage/events*.jsonl` contain real sensor data — must never be edited, exposed, or deleted.
- Phase 8 (Behavioral Federation) has no timeline — blocked on finding two willing pilot operators.

## Test status
Pass (CI 2026-06-11) — `pytest -q` on main. 3 test directories: `tests/unit/` (26 files), `tests/integration/` (26 files), `tests/db/` (10 files). Tests use in-memory SQLite (`DB_PATH=:memory:`) via pytest.ini env config.

## Deployment status
Not publicly deployed. Local only via `make run` (uvicorn :8088) or Docker Compose (`docker/docker-compose.edge.yml`). Current release: v0.34.2.

## Human review required

* **Required:** no — all active backlog items are closed. D2 closed 2026-06-12 after human sign-off.

## Open decisions
- Phase 8 prerequisites — options: wait / proactively seek pilot partners — owner: Stefan — blocking? no

## Notes
- The `docker/docker-compose.edge.yml` references `../ui/backend/Dockerfile`, which exists at `ui/backend/`. The main Makefile does not have a Docker build target — run docker-compose directly.
- Release automation: semantic-release fires on every merge to `main`. Conventional commit type determines version bump.
- The frontend dashboard (`ui/dashboard/`) is React 19 + Vite + TypeScript + Recharts. Dev server: `cd ui/dashboard && npm run dev`.
- `make smoke` includes `POST /api/ingest` — writes a synthetic event to the database. Do not run against real operational data.
