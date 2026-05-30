# DECISION LOG — LegionTrap TI

_Last updated: 2026-05-30 by Claude (onboarding run)_

> Each entry records a decision that is not obvious from reading the code — architectural choices, tradeoffs, rejected alternatives. Read before changing architecture, storage, deployment, or intelligence model.

> **Note:** Entries marked "detected from codebase" are inferred from current implementation/docs and should be treated as operational memory, not guaranteed historical intent, unless confirmed by Stefan.

---

## D-001 — SQLite over PostgreSQL for primary storage
**Date:** Pre-Phase 1 (detected from codebase)
**Decision:** Default storage is SQLite in WAL mode (`storage/legiontrap.db`). PostgreSQL is explicitly supported via SQLAlchemy but not the default.
**Rationale:** Local-first design. The operator owns the data entirely; no managed database service is required. SQLite is sufficient for single-operator honeypot scale.
**Alternatives / tradeoffs noted:** Managed PostgreSQL would add operational complexity/cloud dependency; pure filesystem JSONL appears to have been superseded by SQLite for queryability.
**Migration path:** SQLAlchemy ORM + Alembic make a PostgreSQL migration feasible when scale requires it.

---

## D-002 — Deterministic campaign clustering (no ML)
**Date:** Pre-Phase 4 (detected from architecture docs)
**Decision:** Campaign similarity scoring is deterministic — weighted per-dimension scores, same inputs always produce same output. No machine learning.
**Rationale:** Explainability is an operational requirement. Operators must be able to read per-dimension similarity scores and understand why a source was assigned to a campaign. ML clustering may make this harder unless deliberately designed for explainability.
**Alternatives / tradeoffs noted:** ML clustering approaches such as DBSCAN/k-means or embedding-based similarity may reduce explainability and add operational complexity unless carefully justified.

---

## D-003 — AI reasoning layer is read-only and isolated
**Date:** Phase 5 (detected from architecture docs)
**Decision:** The AI layer never writes to campaign, fingerprint, event, or actor tables. It reads structured data and returns natural-language analysis. It is disabled by default (`AI_BACKEND=none`).
**Rationale:** Ingest path must function without any AI backend. AI is an analysis tool, not a decision layer. Removing the AI layer leaves ingest and clustering fully intact.
**Alternatives rejected:** AI-in-the-loop clustering (would make the pipeline non-deterministic).

---

## D-004 — Conventional commits + semantic-release for versioning
**Date:** Phase 0 or earlier (detected from CI config)
**Decision:** All commits follow conventional commit format. Merges to `main` trigger semantic-release, which bumps version, generates CHANGELOG, and creates a GitHub Release automatically.
**Rationale:** Removes manual versioning decisions; commit messages become the source of truth for changelog content.
**Note:** Breaking changes require `!` suffix on commit type (e.g., `perf!:`).

---

## D-005 — Tests use in-memory SQLite, not fixtures or mocks
**Date:** Detected from pytest.ini
**Decision:** `DB_PATH=:memory:` is set in pytest.ini. All tests run against a real (in-memory) SQLite instance, not mocked repositories.
**Rationale:** Avoids mock/prod divergence. Real SQL queries run in tests, catching schema-level bugs that mocks would miss.
**Note:** This means tests are somewhat slower than pure unit tests but more reliable.

---

## D-006 — PRIVACY_MODE as first-class config, not an afterthought
**Date:** Pre-Phase 3 (detected from architecture and config)
**Decision:** IOC exports support three privacy modes: raw IPs, last-octet masking, and deterministic HMAC hashing. `PRIVACY_MODE` is a first-class env var, not a feature flag.
**Rationale:** Operators may need to share block lists with partners without revealing observed IPs. The intelligence asset (raw data) is separated from the operational artifact (export).

---

## D-007 — AI authority level: may-edit
**Date:** 2026-05-30 by Stefan (explicit instruction)
**Decision:** Claude may edit files on a feature branch. Commits, merges, and deploys require explicit human approval.
**Rationale:** This project is the testing ground for the autonomous Claude Code workflow. The authority level is intentionally permissive for editing but requires human sign-off on persistent state changes.
