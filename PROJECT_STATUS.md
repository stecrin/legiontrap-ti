# PROJECT STATUS — LegionTrap TI

_Last updated: 2026-06-10_

## Current phase
Post-Phase 7 / maintenance and hygiene hardening complete. Phase 7 (Actor Intelligence) is closed. Phase 8 (Behavioral Federation) is conditional on operational prerequisites (two willing pilot operators + validated fingerprint serialization format).

## Project priority
- **Level:** high
- **Reason:** Active development testing ground for autonomous Claude Code workflow; real sensor data in use; production-like local deployment.

## Production risk level
- **Level:** medium
- **Why:** Live SQLite database (`storage/legiontrap.db`) and real event JSONL files are present in the repo root. Not publicly deployed, but data is operational. 15 Alembic migrations are in place — schema changes carry rollback risk.

## Active branch
`main` (no active feature branch)

## AI authority level
`may-edit` — Claude may edit files on a feature branch, but must not commit, merge, or deploy without explicit human approval.

## Current Agile context
- **Current epic:** Testing infrastructure hardening
- **Current story:** C1 — review and extend actor endpoint test coverage
- **Acceptance criteria:** Coverage report reviewed for `tests/integration/test_actor_endpoints.py`, `test_actor_stability_endpoints.py`, `test_actor_suggestions_endpoints.py`; gaps identified and filled.
- **Backlog:** see `PROJECT_BACKLOG.md`

## Last completed task
2026-06-10 — Security CI gates enabled: `bandit` and `pip-audit` are now blocking CI steps (PR #82). Also completed: documentation hygiene pass (PR #81) and SQLAlchemy `sa.Real` → `sa.REAL` migration compatibility fix (PR #80).

## Next task

* **Action:** C1 — Review and extend test coverage for actor endpoints.
* **Why it matters:** Actor Intelligence (Phase 7) is the most recently shipped subsystem. Integration tests exist but edge-case coverage is unknown.
* **Done when:** Coverage report reviewed; gaps identified and filled for `tests/integration/test_actor_endpoints.py`, `test_actor_stability_endpoints.py`, `test_actor_suggestions_endpoints.py`.

## Commands / tests last run
- **Command:** `pytest -q`, `black --check .`, `ruff check .`, `bandit -r app/ -ll`, `pip-audit`
  **Result:** All pass (CI run 27300795938 on PR #82, 2026-06-10)
  **Date:** 2026-06-10
  **Notes:** Bandit and pip-audit are now blocking gates. 5 verified B608 false positives suppressed with `# nosec B608`. pip-audit clean.

## Known risks
- `storage/legiontrap.db` and `storage/events*.jsonl` contain real sensor data — must never be edited, exposed, or deleted.
- Phase 8 (Behavioral Federation) has no timeline — blocked on finding two willing pilot operators.

## Test status
Pass (CI 2026-06-10) — `pytest -q` on main. 3 test directories: `tests/unit/` (26 files), `tests/integration/` (26 files), `tests/db/` (10 files). Tests use in-memory SQLite (`DB_PATH=:memory:`) via pytest.ini env config.

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
