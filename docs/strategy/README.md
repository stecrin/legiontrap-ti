# LegionTrap TI — Strategy Intelligence Layer

**Document type:** Governance and orientation for the strategy layer
**Audience:** Founders, maintainers, strategic contributors, autonomous agents
**Last reviewed:** 2026-05-23

---

## Purpose of This Layer

The `docs/strategy/` directory is the **living reasoning layer** of the project. It is where strategic thinking happens before it solidifies, where decisions are recorded after they are made, where forecasts are preserved even when uncertain, and where rejected ideas are kept so they are not revisited without cause.

It is distinct from `docs/` in the following way:

| `docs/` — Engineering and Strategic Reference | `docs/strategy/` — Strategic Intelligence Layer |
|---|---|
| Describes what exists and what is planned | Records why decisions were made and what was rejected |
| Stable; changes when architecture or roadmap changes | Living; updated as understanding evolves |
| Authoritative for engineering decisions | Authoritative for strategic reasoning and context |
| Consumed by engineers and autonomous agents | Consumed by founders, strategic contributors, and future maintainers |
| No hypotheses — only validated directions | Explicitly tracks hypothesis confidence levels |

Neither layer is subordinate. They serve different purposes and are updated by different processes.

---

## The Doctrine Lifecycle

Strategic ideas move through four stages. Each stage has a distinct document home and a distinct confidence level.

### Stage 1: Brainstorming

**Where it lives:** `FOUNDER_NOTES.md` or inline notes.
**What it is:** A rough idea, an observation, a hunch, a question. Not yet validated. Not yet useful for decision-making.
**Confidence level:** Low. May be wrong. May be incomplete.
**Examples:** "Could we monetize the federation network directly?" / "Would MSPs pay per-client?"

### Stage 2: Candidate Insight

**Where it lives:** The relevant working document (e.g., `MONETIZATION_STRATEGY.md`, `COMPETITOR_ANALYSIS.md`) with a status tag of `[hypothesis]`.
**What it is:** A claim that has been thought through, that has some supporting logic, but has not been tested in the market or validated by evidence.
**Confidence level:** Medium. Has reasoning behind it. Could be tested.
**Examples:** "Support contracts become viable at Phase 3–4 maturity because that is when operators have production dependencies."

### Stage 3: Validated Insight

**Where it lives:** The relevant working document with a status tag of `[validated]`.
**What it is:** A hypothesis that has been confirmed by evidence — market signals, early adopter feedback, comparable project data, or first-hand validation.
**Confidence level:** High. Should influence near-term decisions.
**Examples:** "Homelab operators are the fastest early adopters of self-hosted security tools." (confirmed by Pi-hole, AdGuard Home, Wazuh adoption patterns)

### Stage 4: Canonical Doctrine

**Where it lives:** Promoted to `docs/` layer — `FOUNDING_PRINCIPLES.md`, `BUSINESS_MODEL.md`, `POSITIONING.md`, or the relevant canonical document.
**What it is:** A validated insight that is stable enough to be treated as a standing constraint or principle.
**Confidence level:** Definitive. Governs decisions until explicitly revised.

---

## How Ideas Move Between Stages

Movement is explicit, not implicit. An idea does not automatically become canonical because time has passed.

**Brainstorming → Candidate Insight:**
The author writes up the idea with supporting reasoning and adds it to the relevant working document with a `[hypothesis]` tag. No review required; the author is responsible for the reasoning quality.

**Candidate Insight → Validated Insight:**
Evidence is documented alongside the claim. Evidence may be: market signals (adoption data, community feedback), analogous project history (comparable open-source tools), or first-hand operator feedback. The author updates the tag to `[validated]` and adds a citation to the evidence.

**Validated Insight → Canonical Doctrine:**
A maintainer reviews the validated insight and decides it is stable enough to govern future decisions. The insight is promoted to the relevant `docs/` document with appropriate integration into the canonical framework. The strategy document retains a note: "Promoted to [document] on [date]."

**Any Stage → Rejected:**
Any idea at any stage may be moved to `REJECTED_IDEAS.md` with a documented rationale. Rejection preserves the idea — it does not erase it.

---

## How Contradictions Are Resolved

When a strategy document contradicts an engineering or architectural document in `docs/`, the `docs/` document governs unless the contradiction represents a deliberate strategic revision.

When a contradiction is found between two strategy documents:
1. Identify which document has higher-confidence claims (validated vs. hypothesis)
2. If both are validated, bring the conflict to maintainer review
3. Document the resolution in `STRATEGY_CHANGELOG.md`
4. Update both documents to reflect the resolved position

When a strategy document contradicts a founding principle (`FOUNDING_PRINCIPLES.md`):
- The founding principle governs
- If the founding principle needs to change, that change requires explicit maintainer decision and a `STRATEGY_CHANGELOG.md` entry explaining the rationale

---

## Strategic Memory Philosophy

### Why preserve rejected ideas

A rejected idea that is not recorded will be re-proposed. The cost of re-evaluating an idea that was carefully rejected is time and energy spent on a dead end. `REJECTED_IDEAS.md` is the mechanism that prevents strategic loops.

An idea in `REJECTED_IDEAS.md` is not permanently dead. It includes a section on "what would need to change to reconsider this." When circumstances change sufficiently, a rejected idea can be re-opened through a named process rather than through gradual drift.

### Why preserve decision rationale

Decisions made without recorded rationale will be second-guessed, relitigated, or reversed by people who did not understand the original reasoning. `STRATEGIC_DECISIONS.md` is the mechanism that gives future contributors and maintainers the context to understand why things are the way they are.

### Why maintain forecasts

Forecasts that are not written down cannot be evaluated retrospectively. If a forecast about AI attack timing is made in 2026 and turns out to be wrong in 2029, that feedback is valuable — it should update the forecasting model. If the forecast was never recorded, the feedback cannot be used. `AI_THREAT_FORECASTS.md` preserves forecasts with the reasoning that generated them, enabling retrospective evaluation.

### Why separate founder reasoning

The founder's observations and intuitions are inputs to strategy, not outputs. They belong in `FOUNDER_NOTES.md` where they can be read as context, not in canonical documents where they might be mistaken for validated doctrine. Some founder intuitions turn out to be correct and get promoted; others turn out to be wrong and get rejected. Keeping them separate preserves the clarity of the canonical layer.

---

## Governance Principles

### The strategy layer is maintained by maintainers, not by autonomous agents

Autonomous agents may read this layer for context and may propose additions or modifications through the standard PR process. They may not directly update `STRATEGIC_DECISIONS.md`, `REJECTED_IDEAS.md`, or `STRATEGY_CHANGELOG.md` without explicit maintainer instruction. These are the project's strategic memory; they require human judgment for updates.

Autonomous agents may update working documents (`COMPETITOR_ANALYSIS.md`, `AI_THREAT_FORECASTS.md`) with clearly tagged `[hypothesis]` additions when instructed to research and document strategic questions.

### Status tags are mandatory for claims in working documents

Every factual claim in a working document that is not yet canonical must carry one of these tags:
- `[hypothesis]` — reasoning exists, no external validation
- `[validated]` — supported by evidence (cite the evidence)
- `[rejected]` — superseded; see REJECTED_IDEAS.md
- `[promoted]` — moved to canonical docs; entry kept for history

Claims without tags in working documents are a documentation error and should be tagged on the next review.

### Review cadence

The strategy layer should be reviewed in full at least twice per year, or when:
- A major roadmap phase is completed
- A significant competitor move changes the landscape
- Early adopter feedback substantially confirms or contradicts a hypothesis
- A founding principle is proposed for revision

Minor updates (adding a hypothesis, logging a decision) do not require a review cycle.

---

## How Future Contributors Should Use This Layer

**If you are joining the project as an engineer:**
Read `STRATEGIC_DECISIONS.md` to understand why the architecture is what it is. Read `REJECTED_IDEAS.md` to avoid proposing directions that were already considered and declined. You do not need to read the full working documents unless you are making strategic decisions.

**If you are joining as a strategic contributor or advisor:**
Start with this README, then read `FOUNDER_NOTES.md` and `STRATEGIC_DECISIONS.md` to understand the project's reasoning history. The working documents (`BUSINESS_MODEL.md`, `COMPETITOR_ANALYSIS.md`, `MARKET_POSITIONING.md`) are your primary working environment.

**If you are an autonomous agent:**
Read this layer for context. Do not update `STRATEGIC_DECISIONS.md`, `REJECTED_IDEAS.md`, or `STRATEGY_CHANGELOG.md` autonomously. Do not promote hypotheses to canonical doctrine without maintainer instruction. Do not add `[validated]` tags without citing specific evidence.

---

## Document Index

| Document | Type | Status | Summary |
|---|---|---|---|
| `README.md` | Governance | Canonical | This document — governance and orientation |
| `BUSINESS_MODEL.md` | Working | Living | Revenue model working analysis; deeper than `docs/BUSINESS_MODEL.md` |
| `MONETIZATION_STRATEGY.md` | Working | Living | Specific pricing hypotheses and experiment design |
| `MARKET_POSITIONING.md` | Working | Living | Positioning hypotheses and confidence assessment |
| `COMPETITOR_ANALYSIS.md` | Working | Living | Living competitive intelligence tracker |
| `GO_TO_MARKET.md` | Working | Living | Stage-gated GTM experiments and success signals |
| `AI_THREAT_FORECASTS.md` | Forecast | Living | AI attack era forecasts with reasoning and timestamps |
| `FEDERATION_ECONOMICS.md` | Analysis | Living | Federation network effects, bootstrap, economics |
| `INVESTOR_NARRATIVE.md` | Contingency | Stable | Prepared narrative for if investment is sought |
| `FOUNDER_NOTES.md` | Personal | Living | Founder reasoning, intuitions, early hypotheses |
| `STRATEGIC_DECISIONS.md` | Log | Append-only | Permanent record of major strategic decisions |
| `REJECTED_IDEAS.md` | Log | Append-only | Preserved rejected concepts with rationale |
| `STRATEGY_CHANGELOG.md` | Log | Append-only | Chronological strategic evolution log |

---

## Relationship to the Main Docs Layer

```
docs/strategy/        docs/
─────────────         ──────────────────────────────────────
FOUNDER_NOTES   ──→   (inputs to) FOUNDING_PRINCIPLES
BUSINESS_MODEL  ──→   BUSINESS_MODEL (canonical position)
COMPETITOR_*    ──→   COMPETITIVE_POSITIONING, MARKET_ANALYSIS
MARKET_POS      ──→   POSITIONING
GO_TO_MARKET    ──→   GO_TO_MARKET (canonical)
AI_FORECASTS    ──→   AI_ROADMAP (when forecasts mature)
FEDERATION_ECON ──→   FEDERATION_VISION
STRATEGIC_DEC   ──→   (rationale behind) ROADMAP, ARCHITECTURE
REJECTED_IDEAS  ──→   (prevents revisiting) any canonical doc
CHANGELOG       ──→   (history behind) all canonical docs
```

---

*This is the governance document for the `docs/strategy/` layer. All other strategy documents are subordinate to the principles defined here.*
