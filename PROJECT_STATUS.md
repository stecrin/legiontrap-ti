# PROJECT STATUS — LegionTrap TI

_Last updated: 2026-06-11 (C2 closed)_

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
- **Current story:** C2 — COMPLETE; D2 — pending human verification
- **Acceptance criteria:** C2: smoke-level API coverage running in CI via isolated in-memory SQLite — satisfied by `tests/unit/test_api_smoke.py` running under `pytest -q`. D2: `docs/LEGIONTRAP_EXPLAINED.md` accuracy confirmed against Phase 7 state — requires human sign-off.
- **Backlog:** see `PROJECT_BACKLOG.md`

## Last completed task
2026-06-11 — C2 closed: smoke-level API coverage is satisfied by the existing `tests/unit/test_api_smoke.py`, which is discovered and run by `pytest -q` in CI. Tests cover health, authenticated and unauthenticated stats and events, and CORS enforcement using `DB_PATH=:memory:` (isolated, no operational data touched). No separate named CI step is required. `make smoke` remains unsuitable for CI without isolated DB design because it writes a synthetic event via `POST /api/ingest`. Prior: C1 completion documentation (PR #88, 2026-06-11).

## Next task

* **Action:** D2 — Verify `docs/LEGIONTRAP_EXPLAINED.md` accuracy against Phase 7 state.
* **Why it matters:** The explanatory documentation was added in PR #77 (2026-05-30). It should accurately reflect Phase 7 (Actor Intelligence) before being treated as authoritative reference material.
* **Done when:** File reviewed and confirmed current — human verification of Phase 7 accuracy required before closing.
* **Owner:** Stefan (human sign-off required; cannot be closed by automated review alone).

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

* **Required:** no — prior onboarding review complete; D2 (LEGIONTRAP_EXPLAINED.md accuracy) pending human verification before that backlog item can be closed.

## Open decisions
- Phase 8 prerequisites — options: wait / proactively seek pilot partners — owner: Stefan — blocking? no

## Notes
- The `docker/docker-compose.edge.yml` references `../ui/backend/Dockerfile`, which exists at `ui/backend/`. The main Makefile does not have a Docker build target — run docker-compose directly.
- Release automation: semantic-release fires on every merge to `main`. Conventional commit type determines version bump.
- The frontend dashboard (`ui/dashboard/`) is React 19 + Vite + TypeScript + Recharts. Dev server: `cd ui/dashboard && npm run dev`.
- `make smoke` includes `POST /api/ingest` — writes a synthetic event to the database. Do not run against real operational data.
