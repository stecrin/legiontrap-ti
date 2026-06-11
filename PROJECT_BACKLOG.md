# PROJECT BACKLOG — LegionTrap TI

_Last updated: 2026-06-11_

> Owner: Stefan. Review and reprioritize before acting on any item.

---

## Epic A — Hygiene & Safety

### A1 — Remove or gitignore committed `.bak` files
**Status: COMPLETE** — PR #78 (2026-06-05): `.bak` files untracked and `.gitignore` updated.
**Priority:** medium (resolved)
**Why:** Multiple `.bak` files were tracked in git (`iocs_pf.py.bak.*`, `main.py.bak.*`, `test_privacy_and_auth.py.bak.*`, `docker-compose.edge.yml.bak`, etc.). These exposed internal refactor history and added noise to diffs.
**Done when:** All `.bak` files are reviewed, then either kept intentionally or removed from tracking going forward and added to `.gitignore`.
**Note:** Git history was not rewritten — backup files removed from tracking only.

### A2 — Clean up root-level temp files
**Status: COMPLETE** — PRs #78 and #79 (2026-06-05): temp files removed and gitignored.
**Priority:** low (resolved)
**Why:** `tmp.log` and `tmp_events_test.jsonl` existed in the repo root as leftover artifacts from manual testing.
**Done when:** Files deleted or gitignored.

### A3 — Ungate `bandit` and `pip-audit` in CI
**Status: COMPLETE** — PR #82 (2026-06-10): 5 verified B608 false positives suppressed with `# nosec B608`; `continue-on-error: true` removed from both security CI steps; both tools exit 0 as blocking gates.
**Priority:** medium (resolved)
**Why:** Both security jobs ran with `continue-on-error: true`, meaning findings never blocked a merge.
**Done when:** Findings triaged; jobs run without `continue-on-error: true`.

---

## Epic B — Phase 8: Behavioral Federation

### B1 — Define fingerprint serialization format
**Priority:** low (blocked)
**Why:** Phase 8 requires a validated wire format for sharing behavioral fingerprints across independent deployments.
**Done when:** Format documented, validated against two real deployments' data.
**Blocked by:** Two willing pilot operators.

### B2 — Recruit pilot operators for federation exchange
**Priority:** low (blocked)
**Why:** Phase 8 cannot begin without two real operators willing to participate.
**Done when:** Two operators confirmed; data exchange agreement in place.
**Blocked by:** Operator outreach.

---

## Epic C — Testing Infrastructure

### C1 — Review and extend test coverage for actor endpoints
**Priority:** medium (in progress)
**Why:** Actor intelligence (Phase 7) is the most recently added subsystem. Integration tests exist (`tests/integration/test_actor_endpoints.py`, `test_actor_stability_endpoints.py`, `test_actor_suggestions_endpoints.py`, `test_actor_linking_endpoints.py`) but coverage of edge cases is unknown.
**Done when:** Coverage report reviewed; gaps identified and filled.
**Progress:** Stage 14A (2026-06-11) identified 8 gaps across the four test files. PR #84 resolved three high-priority gaps: GAP-1 (list ordering), GAP-2 (blank PATCH display_name), GAP-6 (suggestions campaign status filtering). Remaining open gaps: GAP-3 (PATCH empty body, low), GAP-4 (GET /api/actors limit boundaries, medium), GAP-5 (campaign-link evidence round-trip, medium), GAP-7 (PATCH archived→active reactivation, medium), GAP-8 (GET /api/actors/{id}/campaigns limit boundary, low).

### C2 — Add smoke test to CI
**Priority:** low
**Why:** `scripts/smoke.sh` and `make smoke` exist locally but are not part of CI. A fast API smoke test after unit tests would catch startup/routing regressions.
**Done when:** Smoke step added to `ci.yml`.
**Note:** `make smoke` includes `POST /api/ingest` — writes a synthetic event. Any CI smoke step must use an isolated test database, not operational data.

---

## Epic D — Documentation

### D1 — Add frontend setup instructions to README
**Status: COMPLETE** — PR #81 (2026-06-09): `npm install` + `npm run dev` steps added to README Quick Start.
**Priority:** low (resolved)
**Why:** README Quick Start covered the backend only. The React dashboard (`ui/dashboard/`) had no documented setup steps.
**Done when:** README includes `npm install` + `npm run dev` steps for the frontend.

### D2 — Update LEGIONTRAP_EXPLAINED.md status
**Priority:** low
**Why:** The `docs/LEGIONTRAP_EXPLAINED.md` file was added/updated in PR #77 (`f5a755b`, 2026-05-30). Confirm it accurately reflects Phase 7 state.
**Done when:** File reviewed and confirmed current — **human verification of Phase 7 accuracy required before marking complete.**
**Note:** PR #77 (`docs/legiontrap-explained`) likely addressed this item, but the done-when criterion is a human judgment call that has not been formally verified. Do not mark complete without explicit human sign-off.

---

## Icebox (no priority / no timeline)

- Evaluate PostgreSQL migration for scale (currently SQLite only)
- Consider formal OpenAPI documentation generation from FastAPI app
- Verify whether `node_modules` is tracked by Git. If tracked, remove from tracking and add to `.gitignore`; if not tracked, no action needed.
