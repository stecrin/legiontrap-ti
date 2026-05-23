# LegionTrap TI — Strategy Changelog

**Document type:** Append-only chronological strategy log
**Audience:** Founders, maintainers, future contributors
**Last reviewed:** 2026-05-23
**Governance:** Entries are appended chronologically. Existing entries are never modified.

---

## Purpose

This document records how the project's strategic direction has evolved over time — changes to positioning, monetization direction, governance, architectural philosophy, and market understanding. It is the "why did we change direction?" companion to `STRATEGIC_DECISIONS.md` (which records what was decided) and `REJECTED_IDEAS.md` (which records what was rejected).

---

## Entry Format

```
### YYYY-MM-DD: [Title]
**Type:** Positioning / Monetization / Architecture / Governance / Market Understanding
**Summary:** What changed
**Driver:** What caused this change (new data, new understanding, external event)
**Impact:** Which documents were updated; which decisions were affected
```

---

## Changelog

### 2025-10-01: Project Inception — Core Strategic Positions Established
**Type:** Architecture / Positioning / Governance
**Summary:** Initial strategic positions established: local-first architecture, behavioral intelligence over IOCs, Python FastAPI stack, JSONL as interim storage, dual auth model. See SD-001 through SD-005 and SD-010.
**Driver:** Project inception. No prior state.
**Impact:** Defines all baseline docs. All subsequent entries are relative to this baseline.

---

### 2025-10-15: Storage Evolution Strategy Defined
**Type:** Architecture
**Summary:** Explicit SQLite-first, PostgreSQL-later storage strategy established. Overrode initial consideration of PostgreSQL from day one. See SD-003, RI-009.
**Driver:** Assessment that the primary deployment target (homelab/self-hosted operators) would face unnecessary operational burden from a PostgreSQL server requirement at initial deployment.
**Impact:** DATABASE_SCHEMA.md blueprint design. Phase 1 targeting SQLite with PostgreSQL-compatible schema.

---

### 2025-11-01: Open-Core and AGPL Positions Finalized
**Type:** Monetization / Governance
**Summary:** Open-core business model and AGPL-3.0 license adopted. MIT and proprietary alternatives rejected. VC funding path rejected. See SD-006, SD-007, RI-002, RI-004.
**Driver:** Assessment of the business model options available to a sovereignty-focused security tool. Detailed analysis of what each license choice and funding model would do to the project's relationship with its primary constituency.
**Impact:** docs/BUSINESS_MODEL.md, docs/OPEN_SOURCE_STRATEGY.md. LICENSE file and pyproject.toml not yet updated — Phase 0 task.

---

### 2025-11-15: Federation Architecture — Peer-to-Peer Model Confirmed
**Type:** Architecture / Governance
**Summary:** Peer-to-peer federation protocol adopted over centralized model. See SD-008, RI-001.
**Driver:** Analysis of what a centralized federation server would mean for the sovereignty guarantee. Conclusion: any central server — even one operated by the project — is incompatible with the privacy and anti-surveillance philosophy.
**Impact:** FEDERATION_VISION.md design. docs/strategy/FEDERATION_ECONOMICS.md bootstrap problem formalized.

---

### 2026-05-22: Strategic Documentation System Established
**Type:** Governance
**Summary:** Full strategic and technical documentation layer created in docs/. Documents established: VISION.md, POSITIONING.md, MARKET_ANALYSIS.md, ARCHITECTURE.md, ROADMAP.md, AI_ROADMAP.md, BEHAVIORAL_INTELLIGENCE.md, FEDERATION_VISION.md, SECURITY_AUDIT.md, AUTONOMOUS_OPERATIONS.md. PR #14 merged.
**Driver:** Recognition that without a documentation system, architectural and strategic reasoning would be lost between sessions and inaccessible to contributors.
**Impact:** Establishes docs/ as the authoritative reference layer. docs/README.md defines the document hierarchy and reading protocol.

---

### 2026-05-23: Implementation Blueprint Phase Completed
**Type:** Architecture
**Summary:** Phase 1–5 implementation blueprints completed before implementation begins: DATABASE_SCHEMA.md, MIGRATION_GUIDE.md, INGESTION_PIPELINE.md, AI_REASONING_ARCHITECTURE.md. Two consistency review passes caught and corrected 14 issues. PR #15 merged. See SD-009.
**Driver:** Decision to specify architecture before implementing to catch design conflicts early, particularly around the PostgreSQL-compatibility constraint, IP extraction logic, and HoneypotEvent canonical schema.
**Impact:** All Phase 1–5 implementation has a canonical specification. Future contributors and autonomous agents have a clear contract to implement to.

---

### 2026-05-23: Strategic Foundation Documentation Completed
**Type:** Positioning / Monetization / Governance
**Summary:** Five new strategic foundation documents added to docs/: FOUNDING_PRINCIPLES.md, BUSINESS_MODEL.md, OPEN_SOURCE_STRATEGY.md, GO_TO_MARKET.md, COMPETITIVE_POSITIONING.md. These formalize the project's philosophical and market positions that were previously implicit.
**Driver:** Phase B blueprint completion created a natural checkpoint to formalize the strategic foundation before Phase 0–1 implementation begins.
**Impact:** Layer 1 of docs/ now complete. Strategic positions are explicit, documented, and cross-referenced. AGPL rationale, open-core model, and community trust principles are now canonical doctrine.

---

### 2026-05-23: Strategy Intelligence Layer Created
**Type:** Governance
**Summary:** docs/strategy/ layer created. Governance model (four-stage doctrine lifecycle), decision log, rejected ideas log, and working strategy documents established.
**Driver:** Recognition that the canonical docs layer records what is true; a separate layer is needed to record why it is true, what was rejected, and what remains hypothesis.
**Impact:** docs/strategy/ becomes the home for strategic reasoning, working analysis, and institutional memory. Canonical docs remain stable reference material.

---

*Entries are appended chronologically. Existing entries are never modified.*

*Cross-references: [STRATEGIC_DECISIONS.md](STRATEGIC_DECISIONS.md) · [REJECTED_IDEAS.md](REJECTED_IDEAS.md) · [README.md](README.md)*
