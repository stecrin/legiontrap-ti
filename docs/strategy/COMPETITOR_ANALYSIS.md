# LegionTrap TI — Competitor Analysis (Living Tracker)

**Document type:** Working strategy document — competitive intelligence
**Audience:** Founders, maintainers, strategic contributors
**Last reviewed:** 2026-05-23
**Canonical reference:** `docs/COMPETITIVE_POSITIONING.md` (snapshot analysis), `docs/MARKET_ANALYSIS.md` (landscape). This document tracks competitor evolution, threat scenarios, and intelligence gaps.

---

## Relationship to Canonical Docs

`docs/COMPETITIVE_POSITIONING.md` is a point-in-time analysis of each competitor category. This document tracks:
- Changes in competitor direction
- Specific threat scenarios
- Competitive response playbooks
- Intelligence gaps (things we don't know about competitors)

Update this document when competitor moves change the strategic landscape. Update `docs/COMPETITIVE_POSITIONING.md` when those changes are significant enough to revise the canonical position.

---

## Competitive Threat Register

### Threat CT-001: Wazuh Adds AI Reasoning
**Likelihood:** Medium
**Timeframe:** 18–36 months
**Description:** Wazuh integrates an LLM-based analysis layer that produces natural-language summaries of security events. Wazuh already has a large installed base, strong community, and established deployment tooling.
**Impact if realized:** Reduces LegionTrap's AI reasoning differentiation for operators who are already running Wazuh. However, Wazuh's AI would analyze endpoint events, not honeypot behavioral patterns — a different problem domain.
**Strategic response:** Emphasize the behavioral memory and federation layers, which Wazuh's architecture does not support. Emphasize honeypot-specific intelligence synthesis. Accelerate Phase 6 (behavioral memory) to establish clear differentiation before this threat materializes.
**Status:** [hypothesis — no current evidence of this direction from Wazuh]

---

### Threat CT-002: MISP Adds Local AI Reasoning
**Likelihood:** Low-medium
**Timeframe:** 24–48 months
**Description:** MISP integrates a local AI analysis layer that can reason over its IOC database and produce behavioral correlation.
**Impact if realized:** MISP's installed base in the professional TI community is very large. If MISP adds AI reasoning, operators already in the MISP ecosystem may not need a separate platform.
**Strategic response:** LegionTrap's behavioral fingerprinting and campaign memory are architecturally distinct from IOC management — they require a different data model. MISP adding AI over IOC data is different from LegionTrap's behavioral pattern over event stream approach. Emphasize the complementarity: LegionTrap generates structured intelligence; MISP consumes it.
**Status:** [hypothesis — MISP community discussions exist around AI but no concrete direction]

---

### Threat CT-003: A Well-Funded Startup Enters the Sovereign TI Space
**Likelihood:** Medium
**Timeframe:** 12–24 months
**Description:** A new startup launches with VC backing, targeting the self-hosted / sovereign TI space with a modern product, good documentation, and marketing spend.
**Impact if realized:** Could out-execute on specific tactical dimensions (better UI, faster deployment, more sensor integrations). May have misaligned incentives (VC pressure to add cloud features or collect data).
**Strategic response:** The moats that matter here — behavioral memory depth, federation network scale, community trust — are not purchasable with VC money. A well-funded newcomer can build a better UI faster; it cannot purchase years of behavioral history or a trust network. Emphasize these structural advantages. Evaluate whether their architecture actually delivers sovereignty or merely markets it.
**Status:** [hypothesis — no known competitor matching this description as of 2026-05-23]

---

### Threat CT-004: CrowdStrike / SentinelOne Launches Self-Hosted Tier
**Likelihood:** Very low
**Timeframe:** 36+ months
**Description:** A major XDR vendor launches a self-hosted tier with local AI reasoning to compete with sovereign TI tools.
**Impact if realized:** Would bring significant brand recognition and engineering resources into the space. However, these vendors' AI models are trained on cloud-scale endpoint telemetry — not on honeypot behavioral patterns. Their business model depends on cloud data gravity, making a genuine sovereign offering structurally contradictory to their revenue model.
**Strategic response:** If this occurs, treat it as validation of the market thesis. Their self-hosted tier would likely be cloud-connected in practice (even if marketed otherwise). Document the architectural differences and maintain trust-by-verification (open source, auditable behavior).
**Status:** [hypothesis — assessed as low probability given business model incompatibility]

---

### Threat CT-005: T-Pot or DShield Adds Intelligence Layer
**Likelihood:** Medium
**Timeframe:** 12–24 months
**Description:** T-Pot (the most widely deployed honeypot distribution) adds campaign analysis, behavioral fingerprinting, or AI reasoning to its existing collection capability.
**Impact if realized:** T-Pot has strong community adoption and the underlying data collection infrastructure that LegionTrap needs for its intelligence layer. If they add the intelligence layer, the combined platform would be directly competitive.
**Strategic response:** T-Pot's architecture is honeypot-centric (collection, visualization). Adding behavioral intelligence would require significant backend work. LegionTrap's approach (universal ingest API that works with any honeypot including T-Pot) means LegionTrap can benefit from T-Pot's collection capability while adding its own intelligence layer. An integration story ("use LegionTrap as the intelligence backend for T-Pot data") may be more effective than a competitive positioning.
**Status:** [hypothesis — no evidence of this direction from T-Pot maintainers as of 2026-05-23]

---

## Intelligence Gaps

Things we currently do not know about the competitive landscape that matter for strategic decisions:

**Gap 1:** How many independent honeypot operators exist globally? If there are 50,000 serious operators and LegionTrap reaches 1%, that is 500 deployments — a meaningful community. If the number is 5,000, 1% is 50 deployments — a small community. We have no reliable estimate.

**Gap 2:** What are the actual operational pain points of Cowrie/Dionaea/T-Pot operators today? Our assumption is "data generates no intelligence" — but this should be validated through direct conversations with operators, not assumed.

**Gap 3:** What fraction of the target segment is subject to GDPR or similar data residency requirements? This determines how much of the TAM is structurally motivated by sovereignty vs. preferring it.

**Gap 4:** What do early Wazuh and MISP adopters think about the AI features being developed in those communities? Their adoption signals are leading indicators.

---

## Competitor Movement Log

| Date | Competitor | Event | Strategic Implication |
|---|---|---|---|
| 2026-05-23 | All | No significant sovereign TI entrant identified | Window to establish position remains open |

*Update this table when significant competitor moves occur.*

---

*Cross-references: [docs/COMPETITIVE_POSITIONING.md](../COMPETITIVE_POSITIONING.md) · [docs/MARKET_ANALYSIS.md](../MARKET_ANALYSIS.md) · [MARKET_POSITIONING.md](MARKET_POSITIONING.md)*
