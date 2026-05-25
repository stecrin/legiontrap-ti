# LegionTrap TI — Documentation System

**Document type:** Documentation index and navigation guide
**Audience:** Engineers, contributors, autonomous agents, new maintainers
**Last reviewed:** 2026-05-23

---

## Purpose

This directory is the persistent intelligence layer of the LegionTrap TI project. It contains the strategic direction, architectural decisions, operational constraints, and design rationale that are not derivable from reading the code alone.

**The code describes what the system does today. This documentation describes why it was built this way and where it is going.**

New contributors and autonomous agents must read the relevant documents in this directory before making architectural decisions, planning roadmap work, or modifying security-sensitive components. Treating this documentation as optional will produce work that misunderstands the project's constraints and strategic intent.

---

## How Autonomous Agents Should Use These Documents

Autonomous agents operating in this repository should follow this reading protocol:

### Before any task

1. **Read `AUTONOMOUS_OPERATIONS.md` first.** It defines what agents may and may not do, branch discipline, commit discipline, and security invariants. It is the operational rulebook.
2. **Read `SECURITY_AUDIT.md` before touching auth, CORS, or credential-related code.** It catalogues known vulnerabilities and the remediation plan. Do not accidentally fix an issue in a way that contradicts the audit's preferred approach.

### Before any architectural work

3. **Read `ARCHITECTURE.md`** to understand the current component map and known structural issues.
4. **Read `ROADMAP.md`** to understand the required sequencing. Do not build Phase N+2 features before Phase N is stable.

### Before any AI feature work

5. **Read `AI_ROADMAP.md`** for the full AI integration plan and Stage 0 prerequisites.
6. **Read `BEHAVIORAL_INTELLIGENCE.md`** to understand the core concepts the AI layer is built to reason about.

### Before any federation work

7. **Read `FEDERATION_VISION.md`** for the complete protocol design and privacy constraints.

### For strategic decisions

8. **Read `VISION.md`** and `POSITIONING.md` to verify that a proposed change aligns with the project's strategic direction.

---

## Document Hierarchy

Documents are organized into three layers. Higher layers inform lower layers; lower layers must not contradict higher layers.

```
Layer 1: Strategic Foundation
  VISION.md                  — Mission, philosophy, long-term direction
  POSITIONING.md             — Market positioning, competitive analysis, target user
  MARKET_ANALYSIS.md         — Detailed market landscape and opportunity sizing
  FOUNDING_PRINCIPLES.md     — Operating philosophy: what the project is, refuses to become, and values
  BUSINESS_MODEL.md          — Open-core strategy, monetization philosophy, revenue timeline
  OPEN_SOURCE_STRATEGY.md    — AGPL rationale, community governance, contribution rules, privacy guarantees
  GO_TO_MARKET.md            — Community growth, distribution channels, early adopter strategy
  COMPETITIVE_POSITIONING.md — Detailed comparison against SIEM, XDR, SOAR, and specific platforms

Layer 2: Technical Architecture
  ARCHITECTURE.md    — Component map, data flows, storage evolution plan
  ROADMAP.md         — Phased implementation plan (Phases 0–7)
  AI_ROADMAP.md      — AI integration stages and prerequisites
  FEDERATION_VISION.md — Federation protocol design

Layer 2b: Implementation Blueprints (Phase 1–5)
  DATABASE_SCHEMA.md         — Canonical SQL schema; all tables, indexes, seed data
  MIGRATION_GUIDE.md         — JSONL→SQLite migration procedure; Alembic setup; import tool
  INGESTION_PIPELINE.md      — POST /api/ingest specification; normalization; deduplication
  AI_REASONING_ARCHITECTURE.md — Retrieval-then-reason pattern; SQL context queries; prompt design

Layer 3: Operational and Conceptual Reference
  BEHAVIORAL_INTELLIGENCE.md — Core concept: behavioral fingerprinting and campaign memory
  SECURITY_AUDIT.md          — Known vulnerabilities, severity ratings, remediation plan
  AUTONOMOUS_OPERATIONS.md   — Rules for autonomous agent behavior in this repository

Layer 4: Strategy Intelligence Layer  (docs/strategy/)
  strategy/README.md              — Governance: doctrine lifecycle, four-stage promotion model, contribution rules
  strategy/BUSINESS_MODEL.md      — Revenue scenario analysis and sustainability hypotheses
  strategy/MONETIZATION_STRATEGY.md — Pricing hypotheses, experiment design, validation signals
  strategy/MARKET_POSITIONING.md  — Positioning hypotheses and confidence assessment
  strategy/COMPETITOR_ANALYSIS.md — Living competitive intelligence tracker and threat register
  strategy/GO_TO_MARKET.md        — Stage-gated GTM experiments and success metrics
  strategy/AI_THREAT_FORECASTS.md — AI attack era forecasts with reasoning and retrospective tracking
  strategy/FEDERATION_ECONOMICS.md — Network effects, bootstrap strategy, federation economics
  strategy/INVESTOR_NARRATIVE.md  — Contingency investor narrative (not active direction)
  strategy/FOUNDER_NOTES.md       — Personal reasoning, early hypotheses, unvalidated observations
  strategy/STRATEGIC_DECISIONS.md — Append-only permanent record of major strategic decisions
  strategy/REJECTED_IDEAS.md      — Append-only preserved rejected concepts with rationale
  strategy/STRATEGY_CHANGELOG.md  — Append-only chronological strategic evolution log
```

When a lower-layer document appears to contradict a higher-layer document, the higher-layer document governs. The lower-layer document should be updated to resolve the conflict.

**Layer 4 governance:** The strategy layer contains working hypotheses and living analysis. Claims in Layer 4 carry explicit confidence tags (`[hypothesis]`, `[validated]`, `[rejected]`, `[promoted]`). Claims without tags are a documentation error. Layer 4 documents are updated more frequently than Layers 1–3 and are maintained by founders and maintainers, not by autonomous agents (except under explicit instruction).

---

## Document Classification

### Strategic Documents

These documents define intent and direction. They change when the project's strategy changes — rarely.

| Document | Classification | Summary |
|---|---|---|
| `VISION.md` | Strategic | Mission, philosophy, 3–10 year vision, sovereign cyber intelligence concept |
| `POSITIONING.md` | Strategic | Exact positioning statement, target users, competitive differentiation, strategic moat |
| `MARKET_ANALYSIS.md` | Strategic | SIEM/XDR/SOAR/TIP/honeypot/AI security market analysis; regulatory tailwinds; underserved segments |
| `FOUNDING_PRINCIPLES.md` | Strategic | Operating philosophy: why the project exists, what it refuses to become, trust/privacy/AI/sovereignty principles |
| `BUSINESS_MODEL.md` | Strategic | Open-core strategy, hosted vs. self-hosted, enterprise strategy, monetization philosophy, revenue timeline |
| `OPEN_SOURCE_STRATEGY.md` | Strategic | AGPL-3.0 rationale, community trust model, contribution rules, governance philosophy, privacy guarantees |
| `GO_TO_MARKET.md` | Strategic | Community growth, GitHub/YouTube/X/LinkedIn strategy, homelab/MSP/SOC analyst channels, trust-first growth |
| `COMPETITIVE_POSITIONING.md` | Strategic | Detailed comparison vs. Splunk, Sentinel, CrowdStrike, Wazuh, Elastic, Security Onion, XDR, SOAR, honeypot dashboards |

### Technical Documents

These documents define how the system is built and how it will evolve. They change when architecture evolves or new phases are planned.

| Document | Classification | Summary |
|---|---|---|
| `ARCHITECTURE.md` | Technical | Current component map, auth model, data flow, known structural issues, storage evolution |
| `ROADMAP.md` | Technical | Phases 0–7 with exit criteria, sequencing rationale, and anti-patterns to avoid |
| `AI_ROADMAP.md` | Technical | AI integration in 6 stages; backend options; privacy constraints; risk table |
| `FEDERATION_VISION.md` | Technical | Privacy-preserving fingerprint federation; trust tiers; protocol design; privacy attack analysis |
| `DATABASE_SCHEMA.md` | Blueprint | Canonical SQL schema; all tables, indexes, Alembic migration names, seed data, retention policy |
| `MIGRATION_GUIDE.md` | Blueprint | Step-by-step JSONL→SQLite migration; import tool spec; Alembic env.py setup; rollback plan |
| `INGESTION_PIPELINE.md` | Blueprint | `POST /api/ingest` spec; normalization functions; deduplication; Pydantic models; repository interface |
| `AI_REASONING_ARCHITECTURE.md` | Blueprint | Retrieval-then-reason design; 7 context SQL queries; prompt structure; privacy rules; backend config |

### Operational and Conceptual Documents

These documents define constraints, concepts, and rules that must be understood before working on specific areas.

| Document | Classification | Summary |
|---|---|---|
| `BEHAVIORAL_INTELLIGENCE.md` | Conceptual | What behavioral attack memory is; fingerprint components; why it matters more than IOCs |
| `SECURITY_AUDIT.md` | Operational | Known vulnerabilities with severity ratings, file/line references, remediation steps, checklist |
| `AUTONOMOUS_OPERATIONS.md` | Operational | What autonomous agents may/must-not do; branch and commit rules; security invariants |

---

## Navigation by Task Type

### "I want to understand what this project is trying to achieve."

Start: `VISION.md` → `FOUNDING_PRINCIPLES.md` → `POSITIONING.md` → `BEHAVIORAL_INTELLIGENCE.md`

### "I want to understand the business model and open-source strategy."

Start: `FOUNDING_PRINCIPLES.md` → `BUSINESS_MODEL.md` → `OPEN_SOURCE_STRATEGY.md`

### "I want to understand how LegionTrap compares to existing tools."

Start: `COMPETITIVE_POSITIONING.md` → `MARKET_ANALYSIS.md` → `POSITIONING.md`

### "I want to know what the current code does and why it's structured this way."

Start: `ARCHITECTURE.md` → `SECURITY_AUDIT.md`

### "I want to know what to build next."

Start: `ROADMAP.md` → `ARCHITECTURE.md` → the specific phase's cross-referenced document

### "I want to add AI features."

Prerequisite reading: `AI_ROADMAP.md` Stage 0 checklist → `ROADMAP.md` Phase 1–4 → `BEHAVIORAL_INTELLIGENCE.md`

### "I want to understand the federation design."

Start: `FEDERATION_VISION.md` → `BEHAVIORAL_INTELLIGENCE.md` → `ROADMAP.md` Phase 7

### "I am an autonomous agent about to make changes."

Required: `AUTONOMOUS_OPERATIONS.md` → `SECURITY_AUDIT.md` → `ROADMAP.md`

### "I need to make a security-related change."

Required: `SECURITY_AUDIT.md` → `ARCHITECTURE.md` → `AUTONOMOUS_OPERATIONS.md`

---

## Roadmap Phase → Document Map

| Phase | Focus | Primary Document | Supporting Documents |
|---|---|---|---|
| Phase 0 | Security hygiene | `SECURITY_AUDIT.md` | `ARCHITECTURE.md` |
| Phase 1 | SQLite storage | `DATABASE_SCHEMA.md` | `MIGRATION_GUIDE.md`, `ARCHITECTURE.md` |
| Phase 2 | Ingestion API | `INGESTION_PIPELINE.md` | `DATABASE_SCHEMA.md`, `ROADMAP.md` |
| Phase 3 | GeoIP enrichment | `INGESTION_PIPELINE.md` | `DATABASE_SCHEMA.md` |
| Phase 4 | ATT&CK / standard exports | `DATABASE_SCHEMA.md` | `BEHAVIORAL_INTELLIGENCE.md` |
| Phase 5 | First AI integration | `AI_REASONING_ARCHITECTURE.md` | `AI_ROADMAP.md`, `ROADMAP.md` |
| Phase 6 | Behavioral memory | `BEHAVIORAL_INTELLIGENCE.md` | `AI_ROADMAP.md` |
| Phase 7 | Federation | `FEDERATION_VISION.md` | `BEHAVIORAL_INTELLIGENCE.md` |

---

## Document Maintenance

### When to update these documents

- **`ARCHITECTURE.md`:** When a structural component changes (new router, storage migration, auth change).
- **`ROADMAP.md`:** When phases are completed, re-sequenced, or redefined. Update `Current State` table when capabilities change status.
- **`SECURITY_AUDIT.md`:** When a vulnerability is fixed (check the checklist item), a new vulnerability is found, or a severity assessment changes.
- **`AI_ROADMAP.md`:** When an AI stage is completed or the stage prerequisites change.
- **`FEDERATION_VISION.md`:** When protocol design decisions are finalized or changed.
- **`AUTONOMOUS_OPERATIONS.md`:** When the scope of autonomous agent authority is deliberately expanded or restricted.

### What does NOT belong here

- Code-level implementation details that belong in docstrings or inline comments.
- Debugging notes or session-specific context (those belong in git commit messages).
- Ephemeral task tracking (use the conversation context or a task manager).
- Content already covered in `CLAUDE.md` at the project root.

### Cross-reference integrity

Every document ends with a `Cross-references:` footer. When a document is updated in a way that affects cross-referenced content, the cross-referenced documents should be checked for consistency.

---

## Consistency Rules

These rules were established during the documentation review pass (2026-05-22) to prevent future inconsistencies:

1. **Federation API paths** use the `/api/federation/` prefix, matching all other API routes. The canonical endpoint names are `POST /api/federation/contribute`, `GET /api/federation/fingerprints`, `GET /api/federation/status`.
2. **Phase numbering** in ROADMAP.md (Phases 0–7) is the authoritative main-roadmap sequence. FEDERATION_VISION.md's internal implementation sequence uses "Stage" (not "Phase") to avoid numeric collision.
3. **AI_ROADMAP.md stages** are not the same as ROADMAP.md phases. AI Stages 1–6 nest within ROADMAP.md Phases 5–7 and the long-term roadmap. When referencing prerequisites, always cite the ROADMAP.md phase number explicitly.
4. **`HoneypotEvent`** is the canonical Pydantic schema name for a validated event record. Use this name consistently in code and documentation.
5. **`require_jwt_or_api_key`** is the canonical FastAPI dependency name for the shared authorization gate.

---

*This file is the entry point for the documentation system. All other documents are reachable from here.*
