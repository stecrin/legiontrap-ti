# LegionTrap TI — Go-to-Market Working Strategy

**Document type:** Working strategy document — stage-gated GTM experiments
**Audience:** Founders, maintainers, strategic contributors
**Last reviewed:** 2026-05-23
**Canonical reference:** `docs/GO_TO_MARKET.md` (principles and channel strategy). This document contains the experimental layer: specific campaigns, success metrics, and stage-gating.

---

## GTM Readiness Gate

**Current status: GTM BLOCKED — Phase 0–2 not complete.**

Community engagement before the platform meets minimum quality standards will create a first impression that is difficult to recover from. The readiness gate is:
- Phase 0 security hygiene complete (no plaintext password comparison, no wildcard CORS)
- Phase 1 SQLite storage working
- Phase 2 ingestion API working (a sensor can push events over HTTP)
- README accurately describes current capabilities and their limits
- A 10-minute quickstart deployment path exists and has been tested

Do not begin outward-facing community engagement before this gate is cleared.

---

## Stage-Gated GTM Plan

### Stage 1: Internal Alpha (Current)
**Trigger:** Developer deployment, iteration, documentation
**Activities:** No external engagement; focus entirely on Phase 0–2 completion
**Success metric:** Phase 0–2 exit criteria met; README is accurate and complete

### Stage 2: Silent Launch (Post Phase 0–2)
**Trigger:** Phase 0–2 complete; minimum quality gate cleared
**Activities:**
- GitHub repository made public (if not already) with polished README
- Post in 2–3 relevant communities (r/selfhosted, r/homelab, r/netsec) with honest capability description
- Write a technical blog post: "What I've learned running a self-hosted honeypot intelligence platform"
**Success metrics:**
- 10 stars on GitHub within 30 days
- 3–5 operators deploy and report back (GitHub Issues, community threads)
- At least one substantive technical question in an issue or community thread
**What failure looks like:** Zero engagement after 30 days → iterate on README clarity and positioning language

### Stage 3: Technical Content Launch (Post Phase 3)
**Trigger:** GeoIP enrichment working; a demo with geographically enriched events is possible
**Activities:**
- YouTube: 15–20 minute walkthrough showing real honeypot data → enriched events → geographic analysis
- Written post: analysis of a real attack dataset (sanitized) using LegionTrap
- HackerNews "Show HN" post with the blog post
**Success metrics:**
- 100 GitHub stars
- 25+ active deployments
- HN post gets 50+ upvotes / substantive technical comments
**What failure looks like:** YouTube video gets <100 views in 60 days → evaluate whether the content format matches the audience

### Stage 4: AI Reasoning Demo (Post Phase 5)
**Trigger:** AI reasoning producing demonstrably useful output on real data
**Activities:**
- Demo video: "I asked an AI to analyze my honeypot data — here's what it found"
- Conference lightning talk / CFP submission (DEF CON demo track, BSides)
- Academic outreach: email security research groups with demo + offer to help deploy
**Success metrics:**
- 500 GitHub stars
- 100+ active deployments
- At least one academic deployment

### Stage 5: Community Consolidation (Post Phase 6)
**Trigger:** Behavioral memory demonstrating campaign recognition on real data
**Activities:**
- Case study: "LegionTrap recognized a returning actor after 6 months of dormancy"
- Community forum / Discord / Matrix channel for operators
- Documentation translated to 1–2 additional languages (if community volunteers emerge)
**Success metrics:**
- 1,000+ GitHub stars
- 200+ active deployments
- Active community where operators help each other

---

## Specific Experiment Designs

### Experiment E-001: HN Show HN Launch
**Hypothesis:** [hypothesis] A "Show HN: I built a self-hosted behavioral threat intelligence platform" post that is honest about current limitations and what's planned will get a substantive technical discussion and generate initial adopters.
**Target post:** Post the Show HN when Stage 3 readiness is met. Title must be precise: state what it does and what it is. Do not overpromise.
**Success signal:** 50+ upvotes; substantive technical comments; 3+ GitHub stars traceable to the post
**Failure signal:** <20 upvotes; no substantive comments

### Experiment E-002: Security Community Influencer Outreach
**Hypothesis:** [hypothesis] 2–3 well-known security community figures who run their own honeypot infrastructure would try LegionTrap if asked directly and would share their experience if they found it useful.
**Approach:** Direct, honest outreach to 5 specific people whose public work suggests they would be interested. Not mass outreach. Personalized. Acknowledge the platform is early stage. Ask for honest feedback, not promotion.
**Success signal:** 1–2 deploy and share their experience publicly
**Failure signal:** No responses; or responses that identify fundamental UX or capability problems requiring rework

### Experiment E-003: Academic Security Research Outreach
**Hypothesis:** [hypothesis] University security research groups running honeypots would adopt LegionTrap if the value proposition is explained clearly and if the deployment is straightforward.
**Approach:** After Stage 4 readiness: email 10 academic security research groups with a description of the platform and an offer to help with deployment in exchange for feedback.
**Success signal:** 2+ academic deployments; at least one group provides public feedback or cites the platform in a paper
**Failure signal:** No responses after 2 outreach attempts

---

## Channel Hypothesis Confidence

| Channel | Hypothesis | Confidence | Stage |
|---|---|---|---|
| GitHub organic discovery | Strong in tech-savvy security community | [validated for comparable tools] | Stage 2 |
| r/homelab, r/selfhosted | High engagement from natural audience | [hypothesis] | Stage 2 |
| Hacker News Show HN | Appropriate for technical launch | [hypothesis] | Stage 3 |
| YouTube technical walkthroughs | Effective for tools with a demo story | [hypothesis] | Stage 3 |
| Conference talks (DEF CON, BSides) | High credibility signal | [hypothesis] | Stage 4 |
| Academic outreach | Slow but high-quality deployments | [hypothesis] | Stage 4 |
| LinkedIn long-form content | Appropriate for MSP/enterprise segment | [hypothesis] | Stage 5 |
| X/Twitter community engagement | High-context security community present | [hypothesis] | Stage 2+ |

---

*Cross-references: [docs/GO_TO_MARKET.md](../GO_TO_MARKET.md) · [MARKET_POSITIONING.md](MARKET_POSITIONING.md) · [COMPETITOR_ANALYSIS.md](COMPETITOR_ANALYSIS.md)*
