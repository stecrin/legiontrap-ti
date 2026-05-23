# LegionTrap TI — Founder Notes

**Document type:** Personal reasoning layer — hypotheses, motivations, early observations
**Audience:** Future maintainers, strategic contributors
**Last reviewed:** 2026-05-23
**Governance:** This is the founder's working layer. Claims here are explicitly pre-validation. Ideas that become validated are promoted; ideas that fail are moved to REJECTED_IDEAS.md.

---

## About This Document

This is where the reasoning that doesn't yet belong in a canonical document lives. It contains:
- The motivations behind specific design decisions
- Observations that haven't been validated enough to become doctrine
- Hypotheses about where the market is going
- Things that might be wrong but are worth preserving as early thinking

Everything here is explicitly pre-validation. Do not treat these notes as authoritative. They are inputs to the strategy process, not outputs of it.

---

## Why This Was Built

### The observation that started it

The frustration that drove this project is specific: operators who run honeypots or network sensors generate genuinely interesting behavioral data about how they are being attacked, and almost all of that data goes to waste. It gets written to a log file, maybe glanced at occasionally, and then ignored. The intelligence that could be extracted from it — patterns, campaigns, returning actors — is never extracted because the tools to extract it don't exist at a price point or complexity level that small operators can access.

This is not a small gap. There are tens of thousands of operators running Cowrie, Dionaea, T-Pot, pfSense, and similar tools who generate behavioral attack data continuously. The gap between "has attack data" and "gets intelligence from it" is effectively total.

### The sovereignty angle

The reason for the local-first constraint is not primarily philosophical — it is practical. The operators who are most motivated to extract intelligence from their own attack data are also the operators who are most skeptical of sending that data to a commercial platform. A security researcher running honeypots specifically to understand attacker behavior is not going to send that data to a vendor's cloud. A privacy-focused organization that runs its own infrastructure specifically because it doesn't trust cloud providers is not going to send its attack telemetry to a commercial TI platform.

The sovereignty architecture is what makes the platform adoptable by the people who most need it.

### The AI timing

The behavioral intelligence direction was solidified by thinking through what AI does to the threat landscape. The conclusion: AI-generated attacks will make signature-based detection increasingly useless, and the defensive tools that survive will be those built on behavioral patterns that AI variation cannot efficiently defeat. This thesis is described in detail in BEHAVIORAL_INTELLIGENCE.md. Building toward it now, before the inflection, is better than building toward it after.

---

## Hypotheses I Am Not Ready to Make Canonical

### Hypothesis: The homelab community is the entire early distribution channel
**Status:** [hypothesis]
**Reasoning:** The operators who are most likely to adopt LegionTrap in its early form — technically capable, running their own infrastructure, generating attack data, not averse to rough edges — are disproportionately in the homelab and security research community. I do not think the first 1,000 users will come from enterprise procurement; I think they will come from the r/homelab + r/netsec + security CTF community. If this is wrong — if early adoption comes from somewhere unexpected — the GTM strategy needs to be updated.

### Hypothesis: The first meaningful commercial revenue will come from consulting, not subscriptions
**Status:** [hypothesis]
**Reasoning:** Before the platform has enough Phase 4–5 capability to justify a subscription, the operators who are deploying it in production will need help integrating it with their existing stack, migrating their data, and configuring their sensor integration. That is a consulting opportunity. Consulting requires no additional commercial infrastructure; it requires only expertise. If Phase 0–3 produces early adopters with real deployments, consulting should be available by month 6–12.

### Hypothesis: The AI reasoning layer will be more compelling than the behavioral memory layer for initial adoption
**Status:** [hypothesis]
**Reasoning:** Behavioral memory is the strategic core — the compounding moat — but it takes time to accumulate. An operator who starts using LegionTrap today gets behavioral memory value in proportion to how long they've been running it. But the AI reasoning layer provides value from day one — the first time an operator gets a natural-language analysis of a 24-hour attack window and it says something they didn't already know. I expect that initial adoption will be driven by the "this generated useful intelligence from my data" experience, not the "it remembered an actor from 6 months ago" experience — even though the second is more strategically important.

### Hypothesis: Federation bootstrap requires 3–5 "anchor" deployments
**Status:** [hypothesis]
**Reasoning:** The federation network has zero value at one deployment. It needs a bootstrap group of operators who are willing to set up peer relationships and exchange fingerprints before the network has scale. My intuition is that 3–5 operators with complementary exposure profiles (e.g., different geographic regions, different service exposure) could generate enough collective intelligence to demonstrate value to new participants. Getting those 3–5 anchor operators to commit to the federation before it has value requires either a trust relationship or a compelling enough demonstration of the platform's individual value that they want to participate in the network. This is a sequencing problem, not a technical problem.

### Hypothesis: LegionTrap's long-term position is more comparable to Pi-hole than to MISP
**Status:** [hypothesis]
**Reasoning:** Pi-hole became the default self-hosted DNS filtering platform not because it was the most technically capable option but because it hit a specific combination of: useful enough out of the box, easy to deploy, aligned with values the community cared about (privacy), and backed by a vocal community of advocates. MISP is excellent at what it does but has high operational complexity and a steep learning curve. LegionTrap should aim to be the platform that a homelab operator recommends to their peer without qualification — "just install LegionTrap" — rather than a platform that requires significant expertise to configure and interpret. This implies strong default behavior, good documentation, and a UI that is accessible before the operator has any behavioral history to work with.

### Hypothesis: The MSP segment is worth targeting in 24–36 months, not now
**Status:** [hypothesis]
**Reasoning:** MSPs need multi-tenant or per-client deployment, role-based access control, automated reporting, and a commercial relationship. None of these exist. Targeting MSPs now would require promising capabilities that aren't built and creating expectations that will damage trust when unmet. The right time to engage MSPs is after Phase 5–6 when the core intelligence value is proven and the platform is mature enough for production MSP use.

---

## Things That Worry Me

### The bootstrap timeline
The most compelling version of LegionTrap — behavioral memory with AI reasoning over a rich event history — requires 12+ months of operation to accumulate enough behavioral history to be meaningfully differentiated. Early adopters will see a useful but not dramatically differentiated platform. The question is whether early utility is enough to sustain those early adopters through the period before the compounding moat becomes visible.

### The spec-to-implementation gap
The blueprint phase produced excellent specifications. The implementation has not started. There is a real risk that the implementation reveals issues with the specifications — edge cases, performance problems, schema decisions that seemed correct but create problems in practice. The specifications are well-reviewed but not battle-tested. When implementation starts, the specifications should be treated as strong guidance, not immutable contracts.

### The AI reasoning quality threshold
The Phase 5 AI reasoning layer will only be valuable if its output is actually useful — not generic, not obvious, not hallucinatory. "Three actors probed SSH from different countries" is not intelligence. "This actor has exhibited the same 2-second probe timing in three separate observation windows over six months, consistent with automated tooling rather than manual testing" is intelligence. The difference between these is the quality and richness of the behavioral context provided to the AI. If the AI reasoning output is too generic to be useful, it will damage the platform's reputation before the behavioral memory layer is mature enough to make it good.

---

## Long-Term Intuitions (May Be Wrong)

**The network effect inflection:** The federation network probably has a critical mass threshold somewhere around 50–100 consistently reporting deployments. Below that, the behavioral intelligence value is marginal. Above it, the network starts to provide early warning value that significantly exceeds what any individual deployment can produce. I don't know where exactly that threshold is, but it likely exists.

**Open standards contribution:** The project's long-term position may be stronger as a contributor to open behavioral threat intelligence standards than as a specific platform. If LegionTrap's fingerprint format becomes an industry standard for behavioral intelligence sharing — the way STIX became a standard for structured threat information — the project's influence persists even as the specific platform evolves.

**AI attack timing:** The AI attack inflection is coming but its timing is uncertain. "3–5 years" (2028–2030) is a guess based on current trends. It could be faster or slower. The behavioral memory architecture is the right preparation regardless of timing; the urgency of building it depends on timing.

---

*Cross-references: [STRATEGIC_DECISIONS.md](STRATEGIC_DECISIONS.md) · [docs/FOUNDING_PRINCIPLES.md](../FOUNDING_PRINCIPLES.md) · [AI_THREAT_FORECASTS.md](AI_THREAT_FORECASTS.md)*
