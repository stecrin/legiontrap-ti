# PROJECT BACKLOG — LegionTrap TI

_Last updated: 2026-05-30 by Claude (onboarding run)_

> Items discovered during initial onboarding. Not prioritized by the operator yet.
> Owner: Stefan. Review and reprioritize before acting on any item.

---

## Epic A — Hygiene & Safety

### A1 — Remove or gitignore committed `.bak` files
**Priority:** medium
**Why:** Multiple `.bak` files are tracked in git (`iocs_pf.py.bak.*`, `main.py.bak.*`, `test_privacy_and_auth.py.bak.*`, `docker-compose.edge.yml.bak`, etc.). These expose internal refactor history and add noise to diffs.
**Done when:** All `.bak` files are reviewed, then either kept intentionally or removed from tracking going forward and added to `.gitignore`.
**Note:** Do not rewrite Git history unless sensitive data or secrets are confirmed.
**Risk:** Low — these are backup files, not production code.

### A2 — Clean up root-level temp files
**Priority:** low
**Why:** `tmp.log` and `tmp_events_test.jsonl` exist in the repo root. These appear to be leftover artifacts from manual testing.
**Done when:** Files deleted or gitignored.
**Risk:** Low.

### A3 — Ungate `bandit` and `pip-audit` in CI
**Priority:** medium
**Why:** Both security jobs run with `continue-on-error: true`, meaning findings never block a merge. The inline TODO confirms this is a known issue.
**Done when:** Findings triaged; jobs run without `continue-on-error: true`.
**Risk:** Medium — could reveal blocking findings that need fixes before ungating.

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
**Priority:** medium
**Why:** Actor intelligence (Phase 7) is the most recently added subsystem. Integration tests exist (`tests/integration/test_actor_endpoints.py`, `test_actor_stability_endpoints.py`, `test_actor_suggestions_endpoints.py`) but coverage of edge cases is unknown.
**Done when:** Coverage report reviewed; gaps identified and filled.

### C2 — Add smoke test to CI
**Priority:** low
**Why:** `scripts/smoke.sh` and `make smoke` exist locally but are not part of CI. A fast API smoke test after unit tests would catch startup/routing regressions.
**Done when:** Smoke step added to `ci.yml`.

---

## Epic D — Documentation

### D1 — Add frontend setup instructions to README
**Priority:** low
**Why:** README Quick Start covers the backend only. The React dashboard (`ui/dashboard/`) has no documented setup steps.
**Done when:** README includes `npm install` + `npm run dev` steps for the frontend.

### D2 — Update LEGIONTRAP_EXPLAINED.md status
**Priority:** low
**Why:** The `docs/LEGIONTRAP_EXPLAINED.md` file was added in the most recent commit (`cfa92ea`). Confirm it accurately reflects Phase 7 state.
**Done when:** File reviewed and confirmed current.

---

## Icebox (no priority / no timeline)

- Evaluate PostgreSQL migration for scale (currently SQLite only)
- Consider formal OpenAPI documentation generation from FastAPI app
- Verify whether `node_modules` is tracked by Git. If tracked, remove from tracking and add to `.gitignore`; if not tracked, no action needed.
