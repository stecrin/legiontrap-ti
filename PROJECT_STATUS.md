# PROJECT STATUS — LegionTrap TI

_Last updated: 2026-06-11 (PR #87)_

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
- **Current story:** C1 — COMPLETE (PR #84, PR #86, PR #87)
- **Acceptance criteria:** Coverage report reviewed for all four actor test files (`test_actor_endpoints.py`, `test_actor_stability_endpoints.py`, `test_actor_suggestions_endpoints.py`, `test_actor_linking_endpoints.py`); all 8 identified gaps addressed.
- **Backlog:** see `PROJECT_BACKLOG.md`

## Last completed task
2026-06-11 — C1 actor endpoint test coverage complete. PR #87 added three final tests (PATCH empty body no-op, actor-campaigns limit boundaries), closing GAP-3 and GAP-8. Prior: PR #86 (GAP-4, GAP-5, GAP-7), PR #84 (GAP-1, GAP-2, GAP-6). All 8 gaps identified in Stage 14A now resolved across PRs #84, #86, and #87.

## Next task

* **Action:** C2 — Add smoke test to CI.
* **Why it matters:** `scripts/smoke.sh` and `make smoke` exist locally but are not wired into CI. A fast API smoke check after unit tests would catch startup and routing regressions.
* **Done when:** A smoke step is added to `ci.yml` using an isolated test database (not `storage/legiontrap.db`). Note: `make smoke` writes a synthetic event via `POST /api/ingest` — any CI smoke step requires an isolated DB design before implementation.
* **Blocked by:** Design decision on test-DB isolation strategy for CI smoke.

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
