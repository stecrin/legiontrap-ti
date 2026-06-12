# PROJECT BACKLOG — LegionTrap TI

_Last updated: 2026-06-12 (Stage 22 sensor integration guide complete)_

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
**Status: COMPLETE** — PRs #84, #86, #87 (2026-06-11): all 8 gaps identified in Stage 14A resolved.
**Priority:** medium (resolved)
**Why:** Actor intelligence (Phase 7) is the most recently added subsystem. Integration tests exist (`tests/integration/test_actor_endpoints.py`, `test_actor_stability_endpoints.py`, `test_actor_suggestions_endpoints.py`, `test_actor_linking_endpoints.py`) but coverage of edge cases was unknown.
**Done when:** Coverage report reviewed; gaps identified and filled.
**Resolution:**
- PR #84 (2026-06-11): GAP-1 (list ordering), GAP-2 (blank PATCH display_name), GAP-6 (suggestions campaign status filtering)
- PR #86 (2026-06-11): GAP-4 (GET /api/actors limit boundaries), GAP-5 (campaign-link evidence round-trip), GAP-7 (PATCH archived→active reactivation)
- PR #87 (2026-06-11): GAP-3 (PATCH empty body no-op), GAP-8 (GET /api/actors/{id}/campaigns limit boundary)
- 114 actor integration tests pass across all four test files (CI run 27349314838).

### C2 — Add smoke test to CI
**Status: COMPLETE** — 2026-06-11: satisfied by existing pytest-based smoke coverage already running in CI.
**Priority:** low (resolved)
**Why:** `scripts/smoke.sh` and `make smoke` exist locally but are not part of CI. A fast API smoke test after unit tests would catch startup/routing regressions.
**Done when:** Smoke step added to `ci.yml`.
**Resolution:** `tests/unit/test_api_smoke.py` is discovered and run by the CI `Tests` step (`pytest -q` in `.github/workflows/ci.yml`). It covers `GET /api/health`, authenticated and unauthenticated `/api/stats` and `/api/events`, and CORS enforcement. `pytest.ini` sets `DB_PATH=:memory:` — no live backend, production secret, or operational database is required. The practical intent of C2 is satisfied.
**Note:** `make smoke` includes `POST /api/ingest` — writes a synthetic event and must not be used against operational data. `scripts/smoke.sh` is read-only but requires a running backend and API key; it is not wired into CI and is not required to close C2.

---

## Epic D — Documentation

### D1 — Add frontend setup instructions to README
**Status: COMPLETE** — PR #81 (2026-06-09): `npm install` + `npm run dev` steps added to README Quick Start.
**Priority:** low (resolved)
**Why:** README Quick Start covered the backend only. The React dashboard (`ui/dashboard/`) had no documented setup steps.
**Done when:** README includes `npm install` + `npm run dev` steps for the frontend.

### D2 — Update LEGIONTRAP_EXPLAINED.md status
**Status: COMPLETE** — 2026-06-12: reviewed Stage 20A–20G, corrections merged PR #90 (commits `cfa705d` / `5069b3a`), human sign-off granted.
**Priority:** low (resolved)
**Why:** The `docs/LEGIONTRAP_EXPLAINED.md` file was added/updated in PR #77 (`f5a755b`, 2026-05-30). Confirm it accurately reflects Phase 7 state.
**Done when:** File reviewed and confirmed current — **human verification of Phase 7 accuracy required before marking complete.**
**Resolution:** Stage 20A full accuracy review confirmed the document substantively accurate against Phase 7 / Actor Intelligence state. Two editorial corrections applied: (1) duplicated/truncated "The three explanations" section removed; (2) "Audit every action" scoped to "Maintain audit trails for ingest and AI-assisted analysis actions". PR #90 merged to main 2026-06-12. Human sign-off granted by Stefan after Stage 20G review.

### D3 — Add sensor integration guide for honeypot operators
**Status: COMPLETE** — PR #94 (2026-06-12): `docs/SENSOR_INTEGRATION.md` added; README linked from API Reference section.
**Priority:** medium (resolved)
**Why:** No operator-facing guide existed for connecting a real honeypot sensor to `POST /api/ingest`. Potential pilot operators needed a clear integration path before evaluation.
**Done when:** Guide covers canonical payload format, sensor-specific field mapping notes (Cowrie VERIFIED, OpenCanary PARTIAL/INFERRED, T-Pot PARTIAL/SENSOR-DEPENDENT), historical backfill via `import_jsonl.py`, continuous forwarding pattern, troubleshooting, and privacy/safety warnings.

---

## Icebox (no priority / no timeline)

- Evaluate PostgreSQL migration for scale (currently SQLite only)
- Consider formal OpenAPI documentation generation from FastAPI app
- Verify whether `node_modules` is tracked by Git — **Verified 2026-06-12 (Stage 21A): not tracked by Git, no action needed.**
- Consider documenting the Docker Quick Start deployment path — deferred from Stage 21C because the current `docker/docker-compose.edge.yml` mounts `../storage:/data:rw` (live sensor data exposure risk); requires a deliberate decision on volume strategy before this is documented as a supported path.
