# PROJECT STATUS — LegionTrap TI

_Last updated: 2026-06-12 (Stage 22 sensor integration guide complete)_

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
2026-06-12 — Stage 22 sensor integration guide complete: `docs/SENSOR_INTEGRATION.md` added — operator-facing guide for connecting real honeypot sensors (Cowrie, OpenCanary, T-Pot) to `POST /api/ingest`. Covers canonical payload format, sensor-specific field mapping notes (Cowrie VERIFIED, OpenCanary PARTIAL/INFERRED, T-Pot PARTIAL/SENSOR-DEPENDENT), historical backfill via `import_jsonl.py`, continuous forwarding pattern, troubleshooting, privacy notes, and operator safety warnings. README linked from API Reference section. Merged PR #94 (commits `aca6734`, `8808d74`, merge commit `2ee69dc`). Prior: Stage 21 onboarding docs complete 2026-06-12 via PR #92.

## Next task

* **Action:** Begin first-wave manual outreach to candidate pilot operators. The sensor integration documentation gap is now closed — `docs/SENSOR_INTEGRATION.md`, the README Quick Start, onboarding documentation, and dashboard guidance are all current and ready for external evaluation. Options: (1) begin direct outreach to candidate operators in the honeypot community; (2) document the Docker deployment path before outreach (storage mount decision required first — see icebox); (3) export OpenAPI spec to lower evaluation friction; (4) hold and revisit when outreach leads emerge.
* **Why it matters:** All technical and documentation preparation is complete. The primary constraint on Phase 8 is adoption, not implementation. Phase 8 entry requires two confirmed pilot operators.
* **Done when:** Stefan selects the next priority and begins outreach, or updates this file to defer.
* **Owner:** Stefan.

## Commands / tests last run
- **Command:** `pytest -q`, `black --check .`, `ruff check .`, `bandit -r app/ -ll`, `pip-audit`
  **Result:** All pass (CI run 27404052699 on PR #92, 2026-06-12)
  **Date:** 2026-06-12
  **Notes:** 1638 tests pass, 3 skipped. Bandit and pip-audit blocking gates remain clean.

## Known risks
- `storage/legiontrap.db` and `storage/events*.jsonl` contain real sensor data — must never be edited, exposed, or deleted.
- Phase 8 (Behavioral Federation) has no timeline — blocked on finding two willing pilot operators.

## Test status
Pass (CI 2026-06-12, PR #92) — `pytest -q` on main. 3 test directories: `tests/unit/` (26 files), `tests/integration/` (26 files), `tests/db/` (10 files). Tests use in-memory SQLite (`DB_PATH=:memory:`) via pytest.ini env config.

## Deployment status
Not publicly deployed. Local only via `make run` (uvicorn :8088) or Docker Compose (`docker/docker-compose.edge.yml`). Current release: v0.34.2.

## Human review required

* **Required:** no — Stage 22 sensor integration guide complete 2026-06-12 (PR #94). All active backlog items are closed.

## Open decisions
- Phase 8 prerequisites — options: wait / proactively seek pilot partners — owner: Stefan — blocking? no

## Notes
- The `docker/docker-compose.edge.yml` references `../ui/backend/Dockerfile`, which exists at `ui/backend/`. The main Makefile does not have a Docker build target — run docker-compose directly.
- Release automation: semantic-release fires on every merge to `main`. Conventional commit type determines version bump.
- The frontend dashboard (`ui/dashboard/`) is React 19 + Vite + TypeScript + Recharts. Dev server: `cd ui/dashboard && npm run dev`.
- `make smoke` includes `POST /api/ingest` — writes a synthetic event to the database. Do not run against real operational data.
