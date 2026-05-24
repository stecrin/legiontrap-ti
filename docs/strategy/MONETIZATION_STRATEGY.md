# LegionTrap TI — Monetization Strategy

**Document type:** Working strategy document — pricing hypotheses and monetization experiment design
**Audience:** Founders, maintainers, strategic contributors
**Last reviewed:** 2026-05-23

---

## Scope

This document covers specific pricing hypotheses, monetization experiment design, and the sequencing logic for commercial activity. It goes beneath `docs/BUSINESS_MODEL.md` (canonical position) and `docs/strategy/BUSINESS_MODEL.md` (scenario analysis) to the level of specific price points, experiment designs, and validation signals.

**Rule for this document:** Do not invent pricing or launch commercial products. This is analysis and hypothesis — not a product roadmap.

---

## Monetization Prerequisites

No monetization attempt should begin before:
1. Phase 0–2 complete (security hygiene, SQLite, ingestion API working)
2. At least 10 production deployments by independent operators
3. At least one operator who has expressed willingness to pay for support or consulting

Attempting to monetize before these prerequisites creates a perception of premature commercialization that will damage community trust with the target segment.

---

## Tier 1: Consulting and Professional Services

### Hypothesis: Consulting is the correct first revenue vehicle
**Status:** [hypothesis]

Consulting requires no commercial infrastructure, no billing system, no support SLA, and no commercial product. It requires expertise and availability. The operators who are most likely to need consulting are those deploying in contexts where the stakes are high enough to justify professional assistance — small healthcare organizations, small financial services firms, university security teams.

**Hypothesized pricing:**
- Deployment assistance: $2,000–$5,000 per engagement (2–5 days)
- Sensor integration (non-standard honeypots): $3,000–$8,000 per integration
- Security stack integration (MISP, SIEM, existing tooling): $4,000–$10,000 per engagement
- Training and onboarding: $1,500/day

**Validation signal:** Three paid consulting engagements at these price points without price resistance indicates the market will pay for professional services.

**Risk:** Consulting is not scalable. Each engagement requires maintainer time. This is appropriate as a bridge revenue source, not as a long-term primary revenue model.

---

## Tier 2: Support Contracts

### Hypothesis: Support contracts become viable at 100+ active deployments
**Status:** [hypothesis]

At 100 active deployments, some percentage of operators will be running the platform in contexts where they would pay for guaranteed support response times. The conversion rate from active deployment to support contract is unknown; comparable open-source projects suggest 2–5%.

**Hypothesized pricing:**
- Standard support ($25–$35/month): Email support, 48-hour response, community forum access
- Priority support ($75–$100/month): 4-hour response for critical issues
- Enterprise support ($300–$500/month): Direct maintainer access, deployment review, custom integrations

**Validation experiment:** At 50 active deployments, email 20 operators who appear to be using the platform seriously (based on GitHub activity, issue reports) and ask: "If we offered a support contract for $X/month, would you pay for it?" If 4+ of 20 say yes, the pricing is in range.

**Key uncertainty:** What fraction of LegionTrap deployments will be in contexts where the operator would pay for support? Homelab operators generally will not; small organizational deployments generally will.

---

## Tier 3: Enhanced AI Reasoning

### Hypothesis: AI tier is viable only after Phase 5 produces demonstrably useful output
**Status:** [hypothesis]

An AI reasoning tier only makes commercial sense if:
1. The baseline AI reasoning (Ollama local) is clearly useful but limited
2. The enhanced tier (better models via Claude API) produces demonstrably better output on real data
3. Operators understand the difference and value it

If the AI reasoning is not useful at the baseline tier, there is nothing to enhance. If operators cannot tell the difference between baseline and enhanced, there is no willingness to pay for the upgrade.

**Hypothesized pricing:**
- Free: Local AI via Ollama backend; basic analysis quality; no rate limits
- Enhanced ($15–$30/month/deployment): Claude API integration; higher reasoning quality; higher rate limits; multi-window analysis
- Team ($50–$100/month): Multiple users; shared analysis history; collaborative notes

**Validation experiment:** After Phase 5 is implemented, run both Ollama and Claude API backends against the same event dataset. Ask 10 alpha testers to rate the output quality of each without knowing which is which. If Claude output is rated significantly better, the quality differentiation exists. If not, the tier design needs revision.

**Risk:** If local LLM quality closes the gap with Claude API over the Phase 5 timeline, the AI tier differentiation weakens. This is likely over a 2–3 year window as local models improve.

---

## Tier 4: Managed Deployment

### Hypothesis: Managed deployment demand is real but premature to pursue before Phase 4–5
**Status:** [hypothesis]

The operator profile that would pay for managed deployment: an organization that has clear security intelligence needs, is technically capable enough to understand and use LegionTrap, but does not have the operational capacity to maintain the infrastructure. Healthcare organizations, small financial services firms, and academic institutions might fit this profile.

**Hypothesized pricing:**
- Small deployment ($150–$250/month): Single-site, limited sensor count, standard support
- Medium deployment ($400–$700/month): Multi-site, unlimited sensors, priority support
- Enterprise ($1,000–$2,500/month): Custom configuration, dedicated environment, SLA

**Key constraint:** Managed deployment requires multi-tenant isolation, backup infrastructure, monitoring, and customer support capacity that does not currently exist. This tier is appropriate to plan and not appropriate to launch before Phase 4–5 maturity and dedicated operational infrastructure.

**Validation experiment:** Ask 5–10 operators at the Phase 3–4 stage: "Would you pay $X/month to have us host and maintain this for you?" If multiple say yes, the demand is real. Do not build the infrastructure until demand is confirmed.

---

## Pricing Philosophy

### The free tier must be genuinely useful
The baseline free tier is not a crippled demo. It provides the full core intelligence capability: ingestion, storage, behavioral analysis, AI reasoning via local backend, federation. An operator running the free tier self-hosted should have access to everything they need to operate a serious threat intelligence capability.

If the free tier is ever experienced as crippled relative to what it used to offer, community trust will be damaged in proportion to the perceived regression.

### Price to the value, not to the cost
Pricing should reflect the value delivered, not the cost of delivery. Support contracts are priced based on what operators would pay for the assurance, not based on the support team's time cost. AI tier pricing is based on what operators would pay for better analysis, not based on Claude API call costs.

### Start high and adjust down; never start low and adjust up
It is structurally easier to reduce prices than to raise them. Initial pricing experiments should be at the high end of the hypothesized range. If operators decline at that price, reduce. If operators accept readily, the price may be too low.

---

## Monetization Anti-Patterns to Avoid

**Usage-based pricing on event volume:** Creates a perverse incentive for operators to reduce telemetry collection to save cost. Degrades the platform's value (less data = less intelligence). See Splunk's volume pricing problem in MARKET_ANALYSIS.md.

**Freemium with timed trials:** "Try premium free for 30 days then pay" manipulates operators into dependency before showing pricing. The target segment is skeptical of this tactic and will resent it.

**Dark patterns and upgrade pressure:** See docs/BUSINESS_MODEL.md. These are explicitly prohibited.

**Premature subscription:** Launching a subscription before the platform provides enough value to justify recurring payment creates a false impression of readiness and will generate churn that damages reputation.

---

*Status tags: [hypothesis] = unvalidated; [validated] = evidence-supported; [rejected] = moved to REJECTED_IDEAS.md*

*Cross-references: [docs/BUSINESS_MODEL.md](../BUSINESS_MODEL.md) · [BUSINESS_MODEL.md](BUSINESS_MODEL.md) · [STRATEGIC_DECISIONS.md](STRATEGIC_DECISIONS.md)*
