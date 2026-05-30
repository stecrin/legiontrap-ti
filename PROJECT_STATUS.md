# PROJECT STATUS — LegionTrap TI

_Last updated: 2026-05-30 by Claude (onboarding run)_

## Current phase
Post-Phase 7 / documentation pass. Phase 7 (Actor Intelligence) is closed. Phase 8 (Behavioral Federation) is conditional on operational prerequisites (two willing pilot operators + validated fingerprint serialization format).

## Project priority
- **Level:** high
- **Reason:** Active development testing ground for autonomous Claude Code workflow; real sensor data in use; production-like local deployment.

## Production risk level
- **Level:** medium
- **Why:** Live SQLite database (`storage/legiontrap.db`) and real event JSONL files are present in the repo root. Not publicly deployed, but data is operational. 15 Alembic migrations are in place — schema changes carry rollback risk.

## Active branch
`docs/legiontrap-explained`

## AI authority level
`may-edit` — Claude may edit files on a feature branch, but must not commit, merge, or deploy without explicit human approval.

## Current Agile context
- **Current epic:** Documentation and onboarding hardening
- **Current story:** Upgrade CLAUDE.md to global framework template + run project onboarding
- **Acceptance criteria:** CLAUDE.md matches global template; PROJECT_STATUS, PROJECT_SUMMARY, PROJECT_BACKLOG, DECISION_LOG created with detected facts; CLAUDE.md commands section populated.
- **Backlog:** see `PROJECT_BACKLOG.md`

## Last completed task
2026-05-30 — CLAUDE.md upgraded to global template format (AI authority: may-edit, placeholders replaced with detected values after onboarding).

## Next task

* **Action:** Review the created memory files (`PROJECT_SUMMARY.md`, `PROJECT_BACKLOG.md`, and `DECISION_LOG.md`) before committing them.
* **Why it matters:** These files now define project memory and future Claude behaviour, so inaccurate assumptions should be corrected before they become trusted context.
* **Done when:** All created memory files have been reviewed and approved or corrected.

## Files changed this session
- `CLAUDE.md` — upgraded to global framework template
- `CLAUDE.md.bak` — backup of original
- `PROJECT_STATUS.md` — created (this file)
- `PROJECT_SUMMARY.md` — created
- `PROJECT_BACKLOG.md` — created
- `DECISION_LOG.md` — created

## Commands / tests last run
- **Command:** not run this session (inspect-only onboarding)
  **Result:** n/a
  **Date:** 2026-05-30
  **Notes:** CI passes on main per GitHub Actions history.

## Known risks
- `bandit` and `pip-audit` run with `continue-on-error: true` in CI — security findings are not blocking. Should be triaged and either fixed or explicitly accepted.
- Multiple `.bak` files committed to the repo (`iocs_pf.py.bak.*`, `main.py.bak.*`, `test_privacy_and_auth.py.bak.*`). These are noise and could expose internal implementation history.
- `tmp.log` and `tmp_events_test.jsonl` in the repo root — leftover temp files, should be gitignored or deleted.
- `storage/legiontrap.db` and `storage/events*.jsonl` contain real sensor data — must never be edited, exposed, or deleted.
- Phase 8 (Behavioral Federation) has no timeline — blocked on finding two willing pilot operators.

## Test status
Pass (last known) — pytest -q on main. 3 test directories: `tests/unit/` (26 files), `tests/integration/` (26 files), `tests/db/` (10 files). Tests use in-memory SQLite (`DB_PATH=:memory:`) via pytest.ini env config.

## Deployment status
Not publicly deployed. Local only via `make run` (uvicorn :8088) or Docker Compose (`docker/docker-compose.edge.yml`). Current release: v0.34.0.

## Human review required

* **Required:** yes
* **Reason:** Onboarding created new project memory files and updated CLAUDE.md. Human review is required before committing these files.

## Open decisions
- Should `.bak` files be deleted or gitignored? — options: delete / gitignore — owner: Stefan — blocking? no
- Should `bandit`/`pip-audit` `continue-on-error` be removed? — options: fix findings first / accept with justification — owner: Stefan — blocking? no
- Phase 8 prerequisites — options: wait / proactively seek pilot partners — owner: Stefan — blocking? no

## Notes
- The `docker/docker-compose.edge.yml` references `../ui/backend/Dockerfile`, which exists at `ui/backend/`. The main Makefile does not have a Docker build target — run docker-compose directly.
- Release automation: semantic-release fires on every merge to `main`. Conventional commit type determines version bump.
- The frontend dashboard (`ui/dashboard/`) is React 19 + Vite + TypeScript + Recharts. Dev server: `cd ui/dashboard && npm run dev`.
