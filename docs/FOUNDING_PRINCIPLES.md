# LegionTrap TI — Founding Principles

**Document type:** Philosophical and operational foundation
**Audience:** Engineers, contributors, autonomous agents, future maintainers, strategic decision-makers
**Last reviewed:** 2026-05-23

---

## Purpose of This Document

This document defines the operating principles of LegionTrap TI — the convictions that govern what gets built, how it gets built, what the project refuses to become, and what it must remain even when commercial or technical pressure suggests otherwise.

These principles are not aspirational marketing language. They are constraints. When a technical decision, a monetization idea, or a feature proposal conflicts with a principle in this document, the principle governs. A project that abandons its principles under pressure is not a project with principles — it is a project with preferences.

---

## Why This Project Exists

### The structural gap

Serious threat intelligence capability currently requires one of two things: a large budget, or a willingness to hand your attack telemetry to a commercial platform. Neither option is available to the majority of security operators who face real threats and need real intelligence.

The operators in this gap — researchers, small teams, privacy-sensitive organizations, self-hosted infrastructure maintainers — are not edge cases. They are the people running the internet's actual infrastructure: university networks, independent media, civil society organizations, small clinics, independent consultants, homelab-scale enterprises. They are consistently targeted and consistently underserved.

LegionTrap exists because this gap should be closed, and because it can only be closed by a tool that is fundamentally different in architecture from the commercial platforms that have failed to serve these operators.

### The architectural conviction

The dominant commercial model in threat intelligence is structurally privacy-extractive. Send us your telemetry; we will enrich it, correlate it, return enriched data, and retain your attack history to improve our models. This model creates value for vendors and creates dependency and exposure for operators.

The architectural alternative — intelligence built locally, on operator-controlled infrastructure, from operator-controlled data, with sharing only when and what the operator explicitly chooses — is not only possible, it is preferable for a large and growing segment of the market. LegionTrap is the implementation of that architectural alternative.

### The timing

Offensive AI is approaching a discontinuity. The cost of generating novel attack variants, coordinating multi-vector campaigns, and adapting to defenses in real time is collapsing. Signature-based and rules-based defenses will be overwhelmed by volume and variation. The defensive tools that survive this transition are tools built on behavioral reasoning and persistent memory — not on signatures or rules.

LegionTrap is being built now, before that transition is complete, specifically to be the right architecture for the post-transition environment. This timing is intentional.

---

## What Problems It Solves

### Problem 1: Attack data that generates no intelligence

Operators running honeypots and network sensors generate valuable behavioral data and extract almost no intelligence value from it. They have logs. They do not have analysis. They cannot answer the questions that matter: Is this a campaign? Have I seen this actor before? Is this related to what I saw six months ago?

LegionTrap solves this by building a persistent behavioral intelligence layer on top of raw event data — enabling campaign recognition, actor tracking, and AI-assisted reasoning that converts raw events into actionable intelligence.

**Current status:** The raw event ingestion infrastructure is implemented. The intelligence layer is planned (Phases 1–6 of the engineering roadmap). This distinction matters: the problem is identified, the architecture is defined, and the implementation has not yet begun.

### Problem 2: No sovereignty in commercial TI

Commercial threat intelligence platforms offer genuine value, but that value comes with a structural cost: the operator's attack data flows to the vendor's infrastructure. For a growing segment of operators — those subject to data residency regulations, those in sensitive sectors, those with principled objections to data concentration — this cost is unacceptable.

LegionTrap solves this by ensuring that event data never leaves operator-controlled infrastructure unless the operator explicitly chooses to share it.

### Problem 3: IOC-based intelligence degrades against AI attackers

IP blacklists and signature databases become obsolete within hours when an attacker rotates infrastructure. AI-generated attacks make every variant unique, defeating signature matching by design.

LegionTrap solves this by building intelligence on behavioral patterns — how actors operate — rather than on what infrastructure they use. Behavioral patterns are far more stable than infrastructure. An actor who changes their IP address every 24 hours still exhibits the same tool signatures, timing distributions, and target selection logic.

**Current status:** The behavioral intelligence concept is fully defined (see BEHAVIORAL_INTELLIGENCE.md). Implementation is planned for Phase 6. This is the strategic core of the platform; it is not yet built.

---

## What This Project Refuses to Become

These are hard limits, not preferences.

### A cloud-dependent SaaS

LegionTrap must always be deployable entirely on operator-controlled infrastructure with no external dependencies. A version that requires a central cloud service, a license check, or a telemetry callback to a vendor server violates the sovereignty value proposition at its foundation.

Commercial offerings may exist alongside the self-hosted core, but the self-hosted core must always function completely independently.

### A data broker

The platform must never aggregate operator event data in a central location that it controls. This applies to any business structure, including future commercial entities associated with this project. Event data belongs to the operator who collected it. The platform is a tool for reasoning over that data, not a collector of it.

This principle extends to behavioral fingerprints shared via federation: the federation protocol must be designed so that no single node — including any node operated by project maintainers — can aggregate and exploit the behavioral patterns of participating operators.

### A compliance theater tool

This platform is not designed to generate compliance reports, produce audit trails for frameworks, or make organizations appear secure for regulatory purposes. It is designed to produce genuine intelligence. If a feature primarily serves compliance appearance rather than operational security, it does not belong in the core.

This is not opposition to compliance — it is insistence on substance over form.

### A black-box intelligence service

Every intelligence conclusion the system produces must be traceable to specific events, specific behavioral patterns, and specific reasoning logic. The system must be capable of explaining why it concluded what it concluded. An operator who disagrees with a conclusion must be able to inspect the underlying evidence and reasoning.

Black-box AI conclusions — numbers or labels with no supporting evidence — are not acceptable in a system that informs security decisions.

### A replacement for human judgment

The system's AI reasoning layer is an analyst aid, not an analyst replacement. It processes data at machine speed and surface patterns a human might miss in the time available. It does not make operational decisions. Blocking decisions, incident response decisions, and attribution judgments are human decisions, informed by the system's analysis.

No AI-generated conclusion should ever trigger an automated blocking action without an explicit operator decision to enable that behavior. The system may suggest; it does not act.

---

## Trust Principles

### The platform earns trust by not requiring it

An operator who deploys LegionTrap should not need to trust that the platform does the right thing with their data. The architecture should make the right behavior verifiable: the code is open, the data flows are local, and no telemetry leaves the system without an explicit configuration action by the operator.

Trust is earned through transparency and architecture, not through promises.

### Trust is binary for data sovereignty

There is no partial sovereignty. If event data can leave the operator's infrastructure under any circumstances that the operator did not explicitly configure and understand, the sovereignty guarantee is violated. This principle applies to crash reports, usage analytics, model training data, and any other mechanism that could transfer event data without explicit operator action.

### Community trust is the prerequisite for adoption

The segment of operators LegionTrap serves — privacy-conscious, technically sophisticated, skeptical of commercial platforms — does not adopt tools that have ambiguous data handling. A single credible report of unexpected data exfiltration, even if minor, destroys adoption in this segment permanently. Community trust, once lost, cannot be recovered by announcement.

This is not a PR consideration. It is an architectural and operational constraint.

### Contributor trust is earned through transparency

Future contributors must be able to trust that their work will not be used in ways that conflict with the project's principles — for example, that open-source contributions will not be incorporated into a proprietary commercial product without acknowledgment or reciprocal commitment.

The license (see OPEN_SOURCE_STRATEGY.md) and governance model must make this guarantee durable, not dependent on the goodwill of any individual.

---

## Privacy Principles

### Local-first as a design constraint, not a feature

Local-first is not a feature that can be removed when inconvenient. Every architectural decision, from storage design to AI reasoning to federation protocol, must be evaluated against the question: does this keep data under operator control?

When a technical choice must be made between a more capable option that requires external data transfer and a less capable option that keeps data local, the local option is the default. Exceptions require explicit operator configuration and explicit documentation.

### Privacy by design, not by option

Privacy protections are built into the data flow, not added as configurable overlays on top of a privacy-unsafe architecture. The privacy masking and hashing features in the IOC export layer demonstrate this: the protection is applied at the export boundary by default, before data leaves the system, not as an afterthought.

The behavioral fingerprint format demonstrates this at the federation layer: fingerprints are designed from the ground up to not contain IP addresses, operator identity, or deployment context. Privacy is in the schema, not in a flag.

### The operator controls what they share

Opt-out is the wrong model for data sharing. Explicit opt-in is the correct model. An operator who has not taken a deliberate configuration action to share data should be confident that nothing is being shared. The default state for any data-sharing feature is disabled.

---

## Anti-Surveillance Philosophy

### Defender tools must not become attacker tools

A system that collects detailed behavioral information about network activity could, in other contexts, be a surveillance tool. LegionTrap is designed for one purpose: helping operators understand attacks against their own infrastructure. The system must be designed to make misuse difficult and visible.

Specific constraints:
- The platform collects events from honeypots and sensors the operator controls and has deployed for the purpose of observing attacks.
- The federation protocol is explicitly designed to prevent any participant from learning which operators are observing which attack patterns.
- The AI reasoning layer operates over the operator's own event data, not over data collected from external systems or users.

### No covert collection

Nothing in the platform should operate without the operator's knowledge. No background processes should communicate with external services unless the operator has explicitly configured and understands those connections. No analytics, telemetry, or usage data should be collected without explicit opt-in.

This applies to the core platform, to commercial tiers built on the core, and to any integrations or plugins associated with the project.

---

## Operational Philosophy

### Foundation before features

The engineering sequencing in ROADMAP.md reflects a principle: it is better to do one thing reliably than to do five things unreliably. Security hygiene before storage. Storage before ingestion. Ingestion before enrichment. Enrichment before AI reasoning. AI reasoning before federation.

Each phase must satisfy its exit criteria before the next begins. A platform that has AI reasoning but cannot reliably store events is worse than a platform that stores events reliably. Premature feature expansion creates technical debt that must be torn out, and in a security tool, it creates the additional risk of giving operators false confidence.

### Correctness over completeness

A system that correctly processes 80% of events and clearly reports on the remaining 20% is better than a system that silently processes 100% with hidden errors. Errors at the data boundary (ingestion, parsing, schema validation) must be surfaced, not swallowed.

This principle applies throughout the stack: where failures happen, they should be visible.

### No permanent decisions before their prerequisites

Architectural decisions that are expensive to reverse — schema design, API contracts, federation protocol format — must not be made before the prerequisites that make them well-informed are in place. This is why the database schema and ingestion pipeline are specified in implementation blueprints before a line of implementation code is written.

### Small teams with long memories

LegionTrap is designed to be operated by small teams. An operator who has been running the system for six months should not need to re-read extensive documentation to understand their own event history. The AI reasoning layer, the campaign memory, and the intelligence archive are designed to make a small team operationally effective over long time scales.

---

## AI Philosophy

### AI as augmentation, not replacement

The AI reasoning layer extends what an operator can learn from their data. It surfaces patterns they would otherwise miss, synthesizes intelligence across time scales, and generates natural-language briefs that compress hours of manual analysis. It does not replace the analyst's judgment about what those patterns mean and what to do about them.

### Grounded reasoning only

Every AI-generated conclusion must be traceable to specific evidence in the event store. The system must cite which events, which behavioral patterns, and which campaign records support a conclusion. Claims that cannot be grounded in specific evidence must not be made. A system that generates confident-sounding but ungrounded analysis is dangerous in a security context.

This is not a limitation. It is a design requirement. The goal is intelligence an operator can act on, not intelligence an operator must fact-check before trusting.

**Current status:** The AI reasoning architecture is fully specified (see AI_REASONING_ARCHITECTURE.md). Implementation is planned for Phase 5. No AI features are currently implemented.

### Multiple backends, one principle

The system supports multiple AI backends: the Claude API (external), Ollama (local inference), and none (AI features disabled). The principle is the same regardless of backend: the AI layer is always additive, never blocking; local operation is always possible; and the operator decides what external services, if any, their intelligence analysis uses.

Operators in air-gapped or regulated environments should have access to all core capabilities using local AI backends.

### Explicit uncertainty

The system must express uncertainty when it is uncertain. A low-confidence behavioral match should be presented differently from a high-confidence one. An actor hypothesis with two supporting data points should be presented differently from one with forty. Calibrated uncertainty is more useful than false confidence.

---

## Local Ownership Philosophy

### Your data, your intelligence, your asset

The behavioral attack history accumulated in a LegionTrap deployment is a genuine intelligence asset. It records who has targeted the operator's infrastructure, how they behaved, and what patterns appeared over time. This asset belongs to the operator and should remain under their control indefinitely, regardless of decisions about platform updates, commercial tiers, or future changes to the project.

An operator must be able to export their complete event history, behavioral fingerprints, and campaign records in standard formats at any time. The platform must never create conditions where data is effectively held hostage to continued platform use.

### Interoperability as a requirement

STIX, MISP, Sigma, ATT&CK, pf.conf, UFW, and standard JSON are not nice-to-have integrations. They are requirements. An operator's intelligence should flow freely to any downstream system they choose to use. The platform that produces intelligence should not be the bottleneck that determines how that intelligence can be used.

**Current status:** pf.conf and UFW exports are currently implemented. STIX, MISP, ATT&CK Navigator, and Sigma exports are planned for Phase 4.

---

## Long-Term Architectural Philosophy

### Standards compliance enables freedom

By implementing standard formats (STIX, MISP, ATT&CK Navigator, Sigma), the platform ensures that intelligence generated within LegionTrap can be consumed by any downstream system. This is the opposite of lock-in. The operator who chooses to migrate away from LegionTrap, add a SIEM, or share intelligence with a partner retains the full value of their historical intelligence.

Proprietary formats that prevent migration or integration are incompatible with the sovereignty philosophy.

### Federation as the long-term differentiator

The architectural decision that determines LegionTrap's long-term strategic position is the privacy-preserving behavioral intelligence federation. When it reaches sufficient scale, the intelligence value of the network — collective behavioral memory across many independent operators — will exceed what any single deployment can accumulate alone.

This is the endgame: not a platform that one operator uses, but a protocol that many operators participate in, each benefiting from the collective intelligence of all participants without any participant sacrificing the sovereignty that defines why they chose a self-hosted platform.

**Current status:** The federation design is fully specified (see FEDERATION_VISION.md). Implementation is planned for Phase 7, following the behavioral memory layer (Phase 6) on which it depends.

### Governance must match the principles

The project's governance structure — licensing, contribution rules, decision-making, commercial relationships — must be designed to make the principles in this document durable rather than dependent on the goodwill of current maintainers.

A project whose principles exist only because the current maintainer chose them, and which can be abandoned when a commercial opportunity appears, does not have principles. It has preferences. The governance model must make the principles structural.

---

*Cross-references: [VISION.md](VISION.md) · [POSITIONING.md](POSITIONING.md) · [ROADMAP.md](ROADMAP.md) · [OPEN_SOURCE_STRATEGY.md](OPEN_SOURCE_STRATEGY.md) · [BUSINESS_MODEL.md](BUSINESS_MODEL.md) · [BEHAVIORAL_INTELLIGENCE.md](BEHAVIORAL_INTELLIGENCE.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
