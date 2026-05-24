# LegionTrap TI — Investor Narrative

**Document type:** Contingency document — prepared narrative for if investment is sought
**Audience:** Founders, maintainers
**Last reviewed:** 2026-05-23
**Status:** Contingency. Investment is not a current priority or direction. See REJECTED_IDEAS.md RI-004 for the reasoning behind the VC funding rejection. This document is prepared in case circumstances change and an investor conversation becomes relevant.

---

## When to Use This Document

This document is preparation, not commitment. It exists so that if an investment conversation ever occurs — an inbound inquiry, a grant opportunity, or a change in strategic direction — the narrative is already structured and internally consistent.

Do not use this document to actively seek investment. The current model (bootstrap, consulting-first, community-led) is the correct model for this project's stage and segment.

Before using this document in any real investor conversation, verify that it still accurately reflects the platform's state and strategic direction. It will become stale as the platform evolves.

---

## The Problem

Security operators running honeypots and network sensors generate valuable behavioral attack data. Almost none of them extract intelligence from it. The tools that could extract that intelligence are either:
- Priced at $50,000–$500,000/year (enterprise platforms like Splunk, Recorded Future)
- Cloud-dependent, requiring operators to send their attack telemetry to a vendor's infrastructure
- Not yet built (the sovereign, AI-powered behavioral intelligence category does not yet have an accessible product)

This is not a niche problem. There are tens of thousands of operators — university security teams, privacy-sensitive organizations, small MSPs, security researchers, self-hosting practitioners — who face real threats, generate real attack data, and have no tool that turns it into intelligence without a cloud dependency or a six-figure budget.

---

## The Solution

LegionTrap TI is a local-first behavioral attack intelligence platform that runs entirely on operator-controlled infrastructure. It:
- Ingests events from any honeypot or network sensor via a standardized HTTP API
- Stores and indexes a queryable event history
- Builds behavioral fingerprints that persist across attacker infrastructure rotation
- Applies AI reasoning to generate natural-language threat intelligence from structured behavioral data
- Exports intelligence in all major standard formats (STIX, MISP, Sigma, ATT&CK Navigator)
- Participates in a privacy-preserving federation that amplifies individual operator intelligence through collective observation

**Current implementation status:** Ingestion infrastructure, dashboard, and IOC exports are implemented. SQLite storage, ingestion API, AI reasoning, and federation are planned across Phases 1–7.

---

## Why Now

The AI attack era is approaching an inflection. The cost of generating novel attack variants, coordinating multi-vector campaigns, and adapting to defenses in real time is collapsing. Signature-based defenses will be overwhelmed by AI-generated variation. The tools that will remain effective are those built on behavioral patterns — how attackers act, not what infrastructure they use.

The 18–24 month window to establish "sovereign behavioral intelligence" as a category, and to establish LegionTrap as the canonical tool in that category, is closing. Community trust and name recognition in the security open-source community, once established, are durable. A later entrant — even well-funded — must spend years building what early execution creates for free.

---

## Why This Team/Approach Wins

**Architectural alignment:** The sovereignty architecture is not a marketing choice — it is the architecture that makes the platform adoptable by the segment it serves. Competitors who build cloud-dependent tools cannot credibly pivot to sovereign architecture without cannibalizing their existing business model.

**Trust as moat:** The security community's trust is earned through consistent behavior over time, not through marketing. A platform that has never violated its sovereignty principles and has always been honest about its capabilities builds trust that a well-funded competitor cannot quickly replicate.

**Behavioral memory depth:** Every deployment that is running builds behavioral history that cannot be purchased. An operator with 3 years of behavioral history has a genuinely better intelligence asset than one with 3 months, and a new deployment cannot purchase that history. This compounding effect creates switching costs that grow with tenure.

**Federation network effect:** Once the privacy-preserving behavioral intelligence federation reaches sufficient scale, the intelligence value of participation grows non-linearly. Network effects that have been proven in adjacent markets (Pi-hole community, MISP adoption) will apply here.

---

## Market Size

The target segment is not Fortune 500 enterprise — it is the large and currently unserved middle: organizations with real security needs, real attack surfaces, and no accessible tool for behavioral intelligence.

**Addressable segment:**
- Security researchers and academics: ~50,000 globally (estimated)
- Small MSPs (5–50 clients): ~15,000–30,000 globally
- Privacy-sensitive organizations (healthcare, legal, civil society): ~100,000 globally
- Self-hosting security practitioners: ~500,000 globally

Commercial opportunity at 1% penetration of the addressable segment at $50–$200/month average revenue: significant.

**Note on sizing:** These are rough estimates. The precise size of the addressable segment is a known intelligence gap (see COMPETITOR_ANALYSIS.md). Sizing should be updated with better data as community engagement begins.

---

## Business Model

Open-core. The core platform is permanently free and AGPL-licensed. Revenue from:
1. Support contracts (current target: Phase 3–4 maturity)
2. Enhanced AI reasoning tier (Phase 5)
3. Managed deployment (Phase 5–6)
4. Enterprise support and professional services (Phase 4+)
5. Managed federation coordination service (Phase 7+)

Target: Bootstrap to sustainability without external investment.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Slow adoption | Strong content marketing, community engagement; trust takes time but is durable |
| Competitor enters space | Behavioral memory depth and federation network effects are structural advantages; moat deepens with time |
| AI reasoning quality insufficient | Multiple AI backends; quality validated before positioning the AI tier commercially |
| Sustainability gap before commercial revenue | Consulting-first bridge strategy; low personal burn rate; community contribution reduces development burden |
| License confusion or dispute | AGPL-3.0 is well-understood; commercial license available for entities requiring proprietary modifications |

---

## What We Are Looking For (If Investment Is Sought)

If investment is ever sought, the criteria are:
1. Investor genuinely understands and commits to the sovereignty architecture (not just acknowledges it)
2. Business model does not require abandoning the open-source core or moving to cloud-first
3. Exit thesis is compatible with the long-term independence of the platform (acquisition by a cloud vendor is incompatible)
4. Investor has experience with open-core developer tools or security infrastructure, not general SaaS

---

*This is a contingency document. Current direction: bootstrap, no investment sought.*

*Cross-references: [STRATEGIC_DECISIONS.md](STRATEGIC_DECISIONS.md) · [REJECTED_IDEAS.md](REJECTED_IDEAS.md) · [BUSINESS_MODEL.md](BUSINESS_MODEL.md) · [MONETIZATION_STRATEGY.md](MONETIZATION_STRATEGY.md)*
