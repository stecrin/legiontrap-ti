# LegionTrap TI — Market Positioning Working Analysis

**Document type:** Working strategy document — positioning hypotheses and confidence assessment
**Audience:** Founders, maintainers, strategic contributors
**Last reviewed:** 2026-05-23
**Canonical references:** `docs/POSITIONING.md` (positioning statement), `docs/MARKET_ANALYSIS.md` (landscape analysis). This document contains positioning hypotheses, confidence levels, and messaging experiments.

---

## Current Positioning Statement
*(From docs/POSITIONING.md — do not duplicate here; reference it)*

> LegionTrap TI is the local-first behavioral attack intelligence system that gives serious security operators AI-powered threat reasoning on data that never leaves their infrastructure.

---

## Positioning Hypotheses

### H-POS-001: "Sovereign intelligence" is a resonant phrase with the target segment
**Status:** [hypothesis]
**Reasoning:** The target segment cares deeply about control over their data. "Sovereign" captures both the privacy dimension and the ownership dimension in a single word. It is not a common marketing term in security, which means it is not yet overloaded with cynicism.
**Test:** Use "sovereign intelligence" in GitHub README and community posts; compare engagement with posts using alternative framings. Measure click-through and comment engagement.
**Risk:** "Sovereign" may read as political to some audiences. Alternative: "operator-controlled intelligence" or "self-sovereign threat intelligence."

### H-POS-002: The "behavioral memory" framing is more compelling than "behavioral analytics"
**Status:** [hypothesis]
**Reasoning:** "Analytics" implies dashboards and charts — familiar and not differentiated. "Memory" implies persistence, accumulation, and the ability to recognize something from the past — which is the actual differentiating capability. An actor who rotates their infrastructure every 24 hours cannot defeat a system that remembers how they behave.
**Test:** Use both framings in community content; track which generates more engagement and more substantive responses.

### H-POS-003: The AI angle is premature for positioning until Phase 5 is built
**Status:** [validated]
**Evidence:** The platform has no AI features today. Positioning against "AI-powered threat reasoning" before the AI layer exists creates an expectation that will not be met and will damage trust when early adopters discover the gap. The positioning should be updated incrementally as capabilities are built.
**Implication:** Near-term positioning should emphasize current capabilities (local-first, behavioral memory direction, sovereignty) without leading with AI claims. AI positioning becomes appropriate when Phase 5 is live and producing useful output.

### H-POS-004: The comparison to Pi-hole is the right mental model for adoption
**Status:** [hypothesis]
**Reasoning:** Pi-hole is the canonical example of a self-hosted tool that became the default recommendation in its category — not because it was technically superior on every dimension, but because it hit the right combination of: useful immediately, easy to deploy, aligned with community values, and backed by genuine advocacy. LegionTrap should aspire to this position in the security self-hosting community.
**Test:** This is a positioning hypothesis about how to describe the project to potential users. Test by using the Pi-hole comparison in community discussions and observing whether it creates recognition.

### H-POS-005: "For operators who cannot send their data to a vendor" is a more precise value proposition than "local-first"
**Status:** [hypothesis]
**Reasoning:** "Local-first" describes an architectural property. "For operators who cannot send their data to a vendor" describes a segment need. The second is more resonant with operators who have a specific constraint (regulatory, ethical, operational) rather than a general preference.
**Risk:** This framing may be too negative (defined by what it doesn't do) rather than positive (defined by what it provides). The best framing is probably a combination: "For operators who cannot send their data to a vendor and want AI-powered behavioral intelligence on their own infrastructure."

---

## Segment Confidence Assessment

| Segment | Fit | Readiness | Confidence |
|---|---|---|---|
| Homelab security operators | High | Early-stage platform appropriate | High |
| Security researchers / academics | High | Needs Phase 3+ for research use | Medium-high |
| Privacy-sensitive organizations (GDPR, healthcare) | High | Needs Phase 0 security fixes first | Medium |
| Small MSPs | Medium | Needs multi-tenant features; not yet | Low |
| Enterprise SOC supplement | Medium-low | Long sales cycle; needs Phase 4–5 | Low |
| Traditional enterprise TI buyers | Low | Wrong architecture, wrong sales model | Very low |

---

## Positioning Risks

### Risk: "Local-first" is misread as "inferior"
A significant portion of potential users may interpret "local-first" as "we couldn't afford to build cloud infrastructure." The counter-narrative: local-first is the architecture of choice for operators who have specific sovereignty requirements, not a capability limitation. This needs to be communicated clearly and proactively.

### Risk: "Behavioral intelligence" is abstract before the capability exists
The behavioral intelligence concept is compelling but abstract to operators who haven't seen it work. Until Phase 5–6 demonstrates it on real data, it is a claim that requires trust. Concrete examples from real (sanitized) attack data are more compelling than abstract capability descriptions.

### Risk: Competing AGPL projects could fragment the community
If another well-executed project enters the sovereign behavioral TI space under AGPL, community fragmentation is possible. The correct response is not defensive positioning — it is staying clearly ahead on capability and execution quality. Network effects from federation make the early-mover advantage significant.

---

## Messaging Experiments to Run (Post Phase 0–2)

1. **GitHub README A/B:** Test "sovereign intelligence" vs. "self-hosted behavioral threat intelligence" in the opening sentence. Measure stars and forks per visitor.
2. **Community post framing:** Post in r/homelab with "I built a self-hosted threat intelligence platform" vs. "I built a behavioral attack memory system for self-hosted operators." Measure upvotes and constructive comment engagement.
3. **The Pi-hole comparison:** "Like Pi-hole but for threat intelligence" as a framing — test in Hacker News launch and community discussions.

---

*Status tags: [hypothesis] / [validated] / [rejected] / [promoted]*

*Cross-references: [docs/POSITIONING.md](../POSITIONING.md) · [docs/MARKET_ANALYSIS.md](../MARKET_ANALYSIS.md) · [COMPETITOR_ANALYSIS.md](COMPETITOR_ANALYSIS.md) · [GO_TO_MARKET.md](GO_TO_MARKET.md)*
