# LegionTrap TI — Strategic Decisions Log

**Document type:** Append-only decision log
**Audience:** Founders, maintainers, future contributors
**Last reviewed:** 2026-05-23
**Governance:** New entries are appended; existing entries are never modified. Corrections are added as follow-up entries referencing the original.

---

## Purpose

This document is the permanent record of significant strategic decisions made during the project's life. Each entry records what was decided, why, what alternatives were considered, and what the expected consequences were.

Future contributors and maintainers should read this document before proposing changes to fundamental architectural or strategic directions. Many decisions here have non-obvious rationale that is not visible in the code or in the current architectural state.

---

## Decision Format

```
### SD-NNN: [Title]
**Date:** YYYY-MM-DD
**Status:** Standing / Revised by SD-NNN / Superseded by SD-NNN
**Decision:** What was decided
**Rationale:** Why this was chosen
**Alternatives considered:** What was evaluated and rejected
**Expected consequences:** What this decision was expected to produce
**Actual outcome:** Updated when known
```

---

## Decisions

### SD-001: Local-First Architecture as a Non-Negotiable Foundation
**Date:** 2025-10-01 (project inception)
**Status:** Standing
**Decision:** LegionTrap is built local-first. Event data never leaves operator-controlled infrastructure by default. All core functionality operates without external network dependencies.
**Rationale:** The target segment (sovereign operators, researchers, privacy-sensitive organizations) is specifically defined by its rejection of cloud-dependent security tools. A cloud-dependent architecture would make the platform structurally incompatible with the segment it is built to serve. This is not a differentiating feature — it is the precondition for adoption in this segment.
**Alternatives considered:** Cloud-first SaaS (rejected — contradicts the sovereignty value proposition); hybrid (rejected — "hybrid" is effectively cloud-first with a local UI; the data still flows to the cloud).
**Expected consequences:** Smaller total addressable market than cloud-first competitors; stronger adoption in sovereign segment; no data-gravity-based upsell path; all revenue must come from services, not data.
**Actual outcome:** Founding principle. Constrains all subsequent architectural decisions.

---

### SD-002: Behavioral Intelligence over IOC-Centric Approach
**Date:** 2025-10-01 (project inception)
**Status:** Standing
**Decision:** The platform's intelligence layer is built on behavioral fingerprinting and campaign memory, not on IP blacklists, file hashes, or traditional IOC sharing.
**Rationale:** IOCs have a structural lifecycle problem: they are generated from past events, shared with delay, consumed by defenders, and then immediately made obsolete by attacker infrastructure rotation. AI-generated attacks accelerate this obsolescence by making every variant unique. Behavioral patterns — how actors operate, not what infrastructure they use — are far more stable. An actor who changes IPs daily still exhibits the same tool signatures and timing distributions.
**Alternatives considered:** IOC-centric TI (rejected — commodity, obsoleting fast, well-served by existing platforms); hybrid IOC + behavioral (deferred — IOC exports are planned for Phase 4 as a compatibility bridge, not as the primary intelligence model).
**Expected consequences:** Longer development timeline before core differentiation is visible (behavioral memory requires Phase 6); strong long-term moat once built; requires more complex infrastructure than an IOC feed.
**Actual outcome:** Informs entire roadmap. The Phase 6 behavioral memory layer is the platform's strategic core.

---

### SD-003: SQLite Before PostgreSQL
**Date:** 2025-10-15
**Status:** Standing
**Decision:** The Phase 1 storage migration targets SQLite, not PostgreSQL. The schema is designed to be PostgreSQL-compatible from day one, but the initial implementation uses SQLite.
**Rationale:** SQLite provides zero additional infrastructure overhead for the primary deployment target (single-operator, self-hosted). File-based backup (copy the `.db` file) is operationally simpler for operators who are not database administrators. Full SQL query capability at SQLite's level is sufficient for all Phase 1–5 query patterns. Concurrent write limitations only become relevant at multi-user or high-volume deployments, which is a Phase 7+ concern.
**Alternatives considered:** PostgreSQL from day one (rejected — requires running a database server, creating a barrier to the homelab/self-hosted segment; adds operational complexity before the platform has proven value to operators); DuckDB (rejected — excellent for analytics but less appropriate for write-heavy event ingestion; less community familiarity).
**Expected consequences:** Simplified deployment for early adopters; migration to PostgreSQL required when concurrent write volume or multi-node deployment needs emerge; PostgreSQL-compatible schema must be enforced from day one to prevent painful migration.
**Actual outcome:** Captured in DATABASE_SCHEMA.md blueprints. Phase 1 implementation not yet started.

---

### SD-004: Dual Authentication Model (JWT + API Key)
**Date:** 2025-10-01
**Status:** Standing
**Decision:** Two distinct authentication mechanisms: JWT bearer tokens for the React dashboard (human users), and API key header (`x-api-key`) for machine-to-machine access (sensors, scripts, CI).
**Rationale:** Human dashboard users expect a session model (login, logout, token expiry). Machine-to-machine access (honeypot sensors, pfSense cron jobs, automation scripts) is inappropriate for JWT — these clients cannot handle token refresh and should use long-lived credentials. The two use cases have different security properties and should use different credential types.
**Alternatives considered:** JWT-only (rejected — machine clients cannot handle token refresh); API-key-only (rejected — session management for human users requires a token model); OAuth (rejected — overengineered for a single-operator tool).
**Expected consequences:** Clean separation of human and machine access paths; `require_jwt_or_api_key` dependency handles both transparently; future multi-user support can extend the JWT path without changing the machine-access path.
**Actual outcome:** Implemented. Known weakness: password verification currently uses plaintext comparison instead of bcrypt. Phase 0 task to fix.

---

### SD-005: Privacy Masking at Export Boundary, Not Storage Time
**Date:** 2025-10-01
**Status:** Standing
**Decision:** Full IP addresses are stored in the event database. Privacy transformation (masking or HMAC tokenization) is applied at the IOC export boundary, not at ingestion or storage time.
**Rationale:** Storage-time masking loses information permanently. If an operator later decides to change their privacy settings, they cannot recover the original data. Export-time masking preserves full fidelity internally while allowing the operator to control what leaves their system. Different exports (pf.conf for blocking, MISP for sharing, internal analysis) may require different privacy levels.
**Alternatives considered:** Storage-time masking (rejected — permanent information loss; cannot change privacy settings retroactively); full IP in all exports (rejected — some operators need to share block lists publicly without revealing their exact observation profile).
**Expected consequences:** Full IP fidelity for internal analysis and campaign correlation; configurable privacy for external sharing; export layer must consistently apply privacy policy.
**Actual outcome:** Implemented in `iocs_pf.py`. Privacy masking and HMAC tokenization working.

---

### SD-006: Open-Core Business Model
**Date:** 2025-11-01
**Status:** Standing
**Decision:** The core platform (ingestion, storage, behavioral analysis, AI reasoning, federation, all exports) is permanently free and open-source. Commercial revenue comes from services: managed deployment, support contracts, professional services, enhanced AI access.
**Rationale:** Gating core intelligence functionality behind a paywall would destroy adoption in the sovereign operator segment, which is also the segment most likely to contribute to and advocate for the platform. The community size that makes a commercial tier viable requires that the core be freely accessible. Revenue from services does not compromise the sovereignty proposition; revenue from feature gates does.
**Alternatives considered:** Fully proprietary (rejected — incompatible with the trust model for this segment); fully open with no commercial path (rejected — unsustainable long-term; core contributors cannot be compensated); tiered feature gates (rejected — would ultimately move intelligence features to paid tiers, destroying the value proposition for the segment that is most motivated by sovereignty).
**Expected consequences:** Slow early revenue; strong community growth prerequisite for commercial viability; commercial viability arrives significantly after Phase 3–4 maturity.
**Actual outcome:** Captured in docs/BUSINESS_MODEL.md. No commercial activity yet; appropriate at current project stage.

---

### SD-007: AGPL-3.0 License
**Date:** 2025-11-01
**Status:** Standing
**Decision:** The project is licensed under AGPL-3.0.
**Rationale:** AGPL closes the network use loophole that MIT and Apache leave open. Under MIT/Apache, a company can run LegionTrap as a cloud service and never contribute modifications back. Under AGPL, network service providers must make modifications available. This prevents commercial free-riding without preventing legitimate commercial use — it merely requires reciprocity.
**Alternatives considered:** MIT (rejected — allows commercial capture without contribution; see SD-007-A in REJECTED_IDEAS.md); Apache 2.0 (rejected — same network-use loophole as MIT); GPL-2.0 (rejected — lacks the network-use clause that makes AGPL appropriate for server software); BSL (Business Source License) (rejected — community skepticism; converts to open-source only after a delay; creates uncertainty during that delay).
**Expected consequences:** Some commercial users will seek a commercial license rather than comply with AGPL disclosure requirements — this is a source of revenue; strong community protection against commercial capture; possible friction with enterprises that have AGPL policies.
**Actual outcome:** License intent established. Not yet reflected in pyproject.toml or LICENSE file — this is a Phase 0 task.

---

### SD-008: Peer-to-Peer Federation over Centralized Model
**Date:** 2025-11-15
**Status:** Standing
**Decision:** The federation protocol is peer-to-peer. No central server collects and redistributes behavioral fingerprints. Operators maintain direct peer relationships.
**Rationale:** A central federation server would be a single point of failure, a single point of surveillance, and a single point of commercial capture. Any entity operating the central server — including the project maintainers — would gain visibility into the behavioral patterns of all participating operators. This is incompatible with the sovereignty and anti-surveillance philosophy. A peer-to-peer model means that even the project maintainers cannot surveil the network.
**Alternatives considered:** Centralized model (rejected — see above; also creates a business model trap where the central server becomes a dependency); hub-and-spoke (rejected — same concerns as centralized with slightly better resilience).
**Expected consequences:** More complex bootstrapping (operators must find and configure peers manually); no central directory of participants; operator privacy is architecturally guaranteed rather than policy-dependent; gossip protocol needed for large-scale propagation.
**Actual outcome:** Captured in FEDERATION_VISION.md. Implementation not yet started (Phase 7).

---

### SD-009: Documentation-First Architecture Specification
**Date:** 2026-05-22
**Status:** Standing
**Decision:** Before implementing Phase 1 storage, a complete implementation blueprint (DATABASE_SCHEMA.md, MIGRATION_GUIDE.md, INGESTION_PIPELINE.md, AI_REASONING_ARCHITECTURE.md) was written and reviewed. Implementation follows the specification, not the other way around.
**Rationale:** The most expensive bugs are architectural bugs — decisions embedded in schemas, API contracts, and data structures that are expensive to change once implementation exists. Writing the specification first surfaces contradictions and design flaws before they become code. The consistency review passes that accompanied the blueprint writing (PR #15) caught 14 issues that would have been buried in implementation.
**Alternatives considered:** Spec-after (rejected — produces drift between intent and implementation; makes refactoring expensive); no spec, just code (rejected — appropriate for prototypes, not for a platform where the schema is a long-lived contract).
**Expected consequences:** Slower start to implementation; higher quality first implementation; clear contract for future contributors and autonomous agents.
**Actual outcome:** PR #15 merged. Blueprints on main. Implementation not yet started.

---

### SD-010: Python FastAPI + React 19 + Vite Stack
**Date:** 2025-10-01 (initial stack selection)
**Status:** Standing
**Decision:** Backend: Python 3.11 + FastAPI + Pydantic. Frontend: React 19 + Vite.
**Rationale:** Python has the strongest ecosystem for security tooling, AI/ML integration (Claude API, Ollama), and behavioral data processing. FastAPI provides high-performance async HTTP with Pydantic schema validation — directly aligned with the HoneypotEvent schema requirements. React + Vite is the standard modern web application stack with minimal operational overhead.
**Alternatives considered:** Go backend (rejected — weaker AI/ML ecosystem; fewer security libraries; more complex for contributors who are primarily Python-fluent security engineers); Flask (rejected — lacks native async, lacks integrated schema validation); Node.js backend (rejected — Python ecosystem advantage is decisive for this use case).
**Expected consequences:** Fast development for Python-fluent security engineers; excellent AI library support; Pydantic schema validation aligns with ingestion pipeline design.
**Actual outcome:** Implemented and working.

---

*New entries are appended in SD-NNN sequence. Existing entries are never modified.*

*Cross-references: [docs/FOUNDING_PRINCIPLES.md](../FOUNDING_PRINCIPLES.md) · [docs/ARCHITECTURE.md](../ARCHITECTURE.md) · [docs/ROADMAP.md](../ROADMAP.md) · [REJECTED_IDEAS.md](REJECTED_IDEAS.md) · [STRATEGY_CHANGELOG.md](STRATEGY_CHANGELOG.md)*
