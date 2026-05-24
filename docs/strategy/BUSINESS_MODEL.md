# LegionTrap TI — Business Model Working Analysis

**Document type:** Working strategy document — deeper analysis beneath the canonical position
**Audience:** Founders, maintainers, strategic contributors
**Last reviewed:** 2026-05-23
**Canonical reference:** See `docs/BUSINESS_MODEL.md` for the stable position statement. This document contains the working reasoning, scenario analysis, and hypotheses behind it.

---

## Relationship to Canonical Document

`docs/BUSINESS_MODEL.md` states the project's business model position. This document contains the reasoning behind that position: the scenarios analyzed, the financial sustainability analysis, the risks, and the hypotheses that have not yet been validated.

Do not duplicate content from the canonical document. Reference it where needed.

---

## The Sustainability Problem

The open-core model creates a specific challenge: the community that makes the commercial tier viable is built by giving away the core product for free. This requires the project to remain useful and actively maintained through the period before commercial revenue exists, which requires maintainer time, which requires either volunteer labor or financial sustainability from a different source.

The three paths to this pre-commercial sustainability:

**Path A: Consulting revenue from early adopters.** The first operators who deploy in production will need integration help, migration assistance, and configuration support. Consulting engagements do not require commercial infrastructure — they require expertise and availability. This is the most immediate viable revenue path.
*Status: [hypothesis] — requires Phase 0–2 completion and early adopter acquisition*

**Path B: Maintainer operating under a day job.** The project is maintained as a significant side project, with commercial activity deferred until adoption reaches a threshold. This is sustainable as long as the project makes meaningful progress and generates enough community validation to justify the investment.
*Status: [validated for early stage] — this is the current operating model*

**Path C: Early institutional partnership.** An academic institution, research group, or privacy-focused organization deploys LegionTrap and provides resources (compute, developer time) in exchange for priority support and influence over the roadmap. This is a grant-like arrangement rather than a commercial one.
*Status: [hypothesis] — would require outreach to security research institutions once Phase 3+ capability exists*

---

## Revenue Scenario Analysis

### Scenario A: Slow Adoption, Consulting-Led
**Timeline:** 36–48 months to modest sustainability
**Mechanism:** Small number of production deployments (10–50); consulting engagements cover maintainer costs; no formal commercial product
**Revenue estimate:** $20K–$80K/year in consulting at this scale
**Risk:** Consultant time competes with development time; difficult to scale
**Validation signal:** First 5 paid consulting engagements

### Scenario B: Community-Driven, Support-Led
**Timeline:** 24–36 months to modest sustainability
**Mechanism:** Larger early adopter community (200–500 deployments); support contract tier becomes viable
**Revenue estimate:** $5K–$15K/month from 20–50 support contracts at $250–$300/month
**Risk:** Support contract adoption rate depends on operators running the platform in contexts where they would pay for support
**Validation signal:** 100 active deployments with operators who identify as production-dependent

### Scenario C: AI-Feature-Led Commercial Tier
**Timeline:** 30–42 months
**Mechanism:** Enhanced AI reasoning tier (better models, higher rate limits) launched after Phase 5 maturity
**Revenue estimate:** $30–$100/month from 100–500 paying organizations
**Risk:** AI reasoning quality must be demonstrably better at the paid tier; free tier must remain genuinely useful
**Validation signal:** Phase 5 completion; 50 operators actively using AI reasoning on production data

### Scenario D: Managed Deployment
**Timeline:** 48–60 months
**Mechanism:** Hosted deployment offering for organizations that want capability without operations
**Revenue estimate:** $200–$600/month per deployment; 30–100 deployments = $6K–$60K/month
**Risk:** Highest operational complexity; requires multi-tenant isolation, backup, monitoring; most capital-intensive
**Validation signal:** Clear demand from organizations that want the capability but cannot operate the infrastructure

---

## The Network Effect Revenue Question

The federation network creates a specific revenue question: once it reaches sufficient scale, is there a component of the federation that generates revenue?

Options analyzed:

**Option 1: Free federation for all** — All tiers get full federation participation. Revenue comes from non-federation services. Maximizes network scale.
*Status: [hypothesis — default direction]*

**Option 2: Enhanced federation coordination service** — Self-managed federation is free. A commercial "managed trust circle" service (verified identity, SLA-backed fingerprint quality, curated feeds) is paid.
*Status: [hypothesis — viable in Scenario D timeline]*

**Option 3: Public behavioral fingerprint commons (paid access)** — A high-quality curated commons of behavioral fingerprints is available to commercial users who pay for the curation and quality guarantee; freely available to self-hosted operators who contribute.
*Status: [hypothesis — very long term; requires significant network scale and curation infrastructure]*

**Rejected option: Raw fingerprint aggregation and resale** — See REJECTED_IDEAS.md RI-011. Not available regardless of revenue potential.

---

## Financial Sustainability Threshold

The minimum viable commercial activity for sustainability:
- Maintainer can spend 20+ hours/week on the project
- Core infrastructure costs (hosting, CI, domain, etc.) are covered
- Some reserve for unexpected costs

Estimated minimum annual revenue for this: $40K–$60K (partial income offset + infrastructure).

At what adoption scale is this achievable?
- Consulting: ~4–6 significant consulting engagements per year at $8K–$15K each
- Support contracts: ~150–200 contracts at $25–$35/month
- Enhanced AI tier: ~400–600 subscriptions at $8–$12/month

Each of these paths reaches the minimum threshold at a different adoption scale. The consulting path reaches it earliest but is least scalable.

---

## Key Validation Milestones

| Milestone | What it validates | Timeline prerequisite |
|---|---|---|
| First 10 production deployments | People will run this in production | Phase 0–2 complete |
| First consulting engagement | Operators will pay for implementation help | Phase 0–2 complete |
| First 100 deployments | Community adoption is real | Phase 2–3 complete |
| First support contract | Operators will pay for ongoing support | Phase 3 complete; 50+ deployments |
| AI reasoning produces useful output | AI tier is viable | Phase 5 complete; user validation |
| First managed deployment inquiry | Hosted tier demand exists | Phase 4–5 complete; enterprise interest |

---

*Status tags: [hypothesis] = unvalidated reasoning; [validated] = supported by evidence; [promoted] = moved to canonical docs*

*Cross-references: [docs/BUSINESS_MODEL.md](../BUSINESS_MODEL.md) · [MONETIZATION_STRATEGY.md](MONETIZATION_STRATEGY.md) · [STRATEGIC_DECISIONS.md](STRATEGIC_DECISIONS.md) · [FOUNDER_NOTES.md](FOUNDER_NOTES.md)*
