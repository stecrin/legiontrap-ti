# LegionTrap TI — Business Model

**Document type:** Strategic — monetization philosophy, commercial model, sustainability plan
**Audience:** Maintainers, contributors, autonomous agents, strategic decision-makers
**Last reviewed:** 2026-05-23

---

## The Governing Constraint

Every revenue model in this document must be compatible with the founding principles: local-first data sovereignty, operator-controlled intelligence, no covert data collection, and open-source community trust. A monetization approach that requires compromising any of these principles is not available, regardless of its revenue potential.

This constraint is not regrettable — it is the source of the competitive moat. Operators in the sovereign-operator segment trust LegionTrap specifically because it cannot monetize their data. Commercial competitors cannot replicate this trust because their business models depend on data access.

---

## Open-Core Strategy

### What open-core means here

Open-core means the foundation of the platform — event ingestion, storage, behavioral fingerprinting, AI reasoning, federation, and standard exports — is free, open-source, and unrestricted. Any operator can deploy the full intelligence capability without a commercial relationship.

The commercial tier is additive: managed deployment, enterprise support, and specific operational conveniences that are valuable to organizations that want the capability without the operational overhead. The commercial tier does not gate core intelligence functionality.

### What is always open-source

The following capabilities must remain open-source and freely available permanently:

- Event ingestion pipeline and schema
- SQLite/PostgreSQL storage layer and migration tools
- Behavioral fingerprint extraction and campaign detection
- All AI reasoning backends (Claude, Ollama, none)
- All standard intelligence exports (STIX, MISP, ATT&CK, Sigma, pf.conf, UFW)
- Federation protocol and client implementation
- Privacy masking and anonymization features
- Dashboard and all UI components

If any of these were moved behind a commercial paywall, the platform would stop being useful for its primary constituency. The value proposition would collapse along with the community trust that makes any commercial tier viable.

### What may be commercial

The following categories are appropriate for commercial differentiation:

**Managed deployment:** Hosted deployment for organizations that want LegionTrap's capabilities without running the infrastructure themselves. This is a service layer, not a software restriction. The operator's data stays in an isolated, operator-controlled environment (not shared with other tenants).

**Enterprise support contracts:** Priority engineering support, deployment assistance, security review, and guaranteed response SLAs for organizations that require formal support commitments.

**Enhanced AI features:** More powerful AI reasoning models, higher API rate limits, and multi-model ensemble analysis. These features enhance quality; they do not block access to baseline AI reasoning, which remains available via local Ollama backends.

**Professional services:** Migration assistance, custom integration development, training, and consulting engagements for organizations integrating LegionTrap into complex security stacks.

**Commercial federation coordination:** For organizations that want a managed trust circle with verified peer identities, curated behavioral fingerprint feeds, and SLA-backed intelligence quality — as an alternative to self-managed peer-to-peer federation.

---

## Hosted vs. Self-Hosted Model

### Self-hosted (primary)

The primary deployment model. The operator downloads the platform, runs it on their own infrastructure, and has complete control over their data, configuration, and upgrade schedule.

Self-hosted is not a "lite" version. It is the full platform. The decision to self-host is a sovereignty decision, not a cost decision — operators choose self-hosting because they want their data on their infrastructure, not because they cannot afford a hosted option.

### Hosted (commercial tier)

A managed deployment offering for organizations that want the intelligence capability without the operational burden. Key characteristics:

- Each organization's deployment is isolated (no shared data store or shared AI reasoning across tenants)
- The operator retains the ability to export their complete data at any time in standard formats
- The hosted offering uses the same open-source codebase; there is no proprietary fork
- Pricing is based on deployment size and support tier, not on data volume ingested

The hosted offering is appropriate for the commercial tier because it provides genuine operational value (reduced burden) without compromising data sovereignty. Each tenant's event data stays in their isolated environment; the hosting provider does not have access to tenant event data.

**Current status:** No hosted offering exists. This is a long-term commercial direction, appropriate after Phase 5–6 capabilities are mature and adoption has reached sufficient scale.

---

## Enterprise Strategy

### Who enterprise means here

"Enterprise" in this context does not mean Fortune 500 compliance departments. It means organizations with operational security requirements that exceed what a single self-hosted deployment handles — multi-site deployments, formal support requirements, audit logging for regulatory purposes, SSO integration, and role-based access control.

Target enterprise segments:
- Universities and research institutions (many sites, academic procurement requirements, research data sovereignty)
- Healthcare organizations (HIPAA data residency, operational scale beyond homelab)
- Critical infrastructure operators (industrial security teams, OT/ICS environments, air-gapped requirements)
- Small-to-medium MSPs (5–50 client organizations requiring shared infrastructure)

### What enterprise does not mean

Enterprise does not mean pivoting toward the same compliance-reporting market that Splunk, Sentinel, and QRadar serve. Competing in that market requires a completely different architecture, sales cycle, and organizational structure. It is the wrong direction.

The enterprise tier serves organizations that need the sovereign intelligence capability at operational scale with enterprise-grade support, not organizations that primarily need audit log aggregation and compliance dashboards.

### Enterprise feature requirements

Enterprise features that do not compromise the open-source foundation:

- Multi-site federation within a single organization's deployment (enterprise private federation)
- Role-based access control (read-only analyst, full admin, API-only ingest)
- SSO integration (SAML, OIDC) for organizations with identity management requirements
- Audit logging for the platform itself (who queried what, when)
- SLA-backed support with defined response times
- Dedicated deployment environments for the hosted tier

---

## Monetization Philosophy

### Trust first, revenue second

Community trust is the prerequisite for any commercial tier. A security tool that is not trusted by the community it serves has no community and therefore no commercial opportunity. The correct sequence is:

1. Build a platform that is genuinely useful and genuinely sovereign
2. Build community trust through consistent behavior over time
3. Offer a commercial tier that provides genuine incremental value
4. Generate revenue from organizations that benefit from the incremental value

Reversing this sequence — attempting to monetize before trust is established, or compromising trust for revenue — destroys the preconditions for the commercial opportunity.

### The product must work without payment

Any operator who chooses to run LegionTrap on their own infrastructure and never pay anyone a dollar must have access to the full core intelligence capability indefinitely. The business model must be sustainable without requiring that every user becomes a customer.

This is not altruism. It is the mechanism by which the community grows large enough to support the commercial tier. A community that cannot use the core product freely is a small community; a small community produces a small commercial tier.

### No dark patterns

The platform must never:
- Show degraded performance to non-paying users to incentivize upgrades
- Send notifications that imply limitations that do not exist
- Require account registration for core functionality
- Collect usage data to target upgrade messaging
- Create artificial friction in the self-hosted path

These tactics are well-understood manipulation techniques. They also destroy trust with exactly the segment — technically sophisticated, skeptical of commercial software — that LegionTrap serves.

---

## Consulting and Support Model

### Community support (always free)

- GitHub Issues for bug reports and feature requests
- Community documentation (public)
- Release notes and upgrade guides

### Commercial support tiers

**Standard support:** Email support with defined response time (48 hours). Appropriate for organizations running production deployments that need assistance but do not have critical SLA requirements.

**Priority support:** Faster response time (4 hours for critical issues). For organizations where LegionTrap is part of active security operations.

**Enterprise support:** Direct access to maintainers, deployment review, security assessment, custom integration assistance. For complex deployments and MSPs running the platform for multiple clients.

### Professional services (project-based)

- Deployment and migration: assisting organizations moving from existing threat intelligence tools or from the JSONL baseline to the full Phase 1–4 implementation
- Custom sensor integration: building ingestion connectors for non-standard honeypot or network monitoring systems
- Security stack integration: integrating LegionTrap's exports with MISP, Elastic, or SIEM deployments
- Training: hands-on training for security teams on behavioral intelligence concepts and platform operation

---

## Premium Feature Philosophy

### The test for a premium feature

A feature belongs in the commercial tier if and only if it meets all three of these criteria:

1. It provides genuine incremental value over the open-source core
2. It does not restrict capabilities that are currently available in the open-source version
3. Its commercialization does not compromise the trust model with the open-source community

A feature that fails criterion 2 (restricts existing open-source capabilities) is the definition of a bait-and-switch. A feature that fails criterion 3 will generate community backlash that costs more than the feature earns.

### Premium features must be services, not feature gates

The appropriate commercial premium is a service layer (managed deployment, support, professional services) rather than a feature gate. A gate says: "you cannot use this feature you previously had access to." A service says: "we will run this and support it for you." These are structurally different and have different trust implications.

Enhanced AI reasoning quality (via more capable models) is an acceptable gate because it is an incremental enhancement over the baseline, not a restriction on existing capabilities. Basic AI reasoning via Ollama remains free; better reasoning via a commercial API can be tiered.

---

## Anti-Trust-Destruction Principles

These are the specific failure modes of open-source commercial projects that destroy community trust. This project must actively avoid them.

### No open-core bait-and-switch

Never move a feature from open-source to commercial after it has been established as part of the open-source offering. This is the most damaging thing an open-core company can do and the one that generates the longest-lasting community resentment.

If a feature is being evaluated for potential commercialization, it must be designed as a commercial feature from the start — not released as open-source and later paywalled.

### No license change without community consensus

The project license (AGPL-3.0 — see OPEN_SOURCE_STRATEGY.md) cannot be changed to a more restrictive or proprietary license without a deliberate community consensus process. License changes that restrict existing freedoms are a form of retroactive trust violation.

If license terms must change for legitimate business reasons, the correct process is to fork a new commercial entity from the existing codebase and allow the open-source project to continue under its original license.

### No data gravity extraction

The commercial tier must never create conditions where an operator's data is effectively locked into the managed platform. Full data export in standard formats must always be available to hosted-tier operators. An operator who wants to leave the managed tier and run self-hosted must be able to take their complete event history with them.

### Transparent commercial relationships

When commercial relationships exist (paid support contracts, managed deployments, enterprise agreements), the terms governing data handling must be explicit and public in their general structure. Operators should never be surprised by how their data is handled.

---

## Long-Term Revenue Layers

Listed in approximate order of viability relative to project maturity.

### Layer 1: Consulting and professional services (early-stage)

Available as soon as the platform has reached Phase 2–3 maturity and has early adopters. Consulting and integration work generates revenue without requiring scale and builds deep relationships with the organizations most likely to become enterprise customers.

**Prerequisite:** A working platform that can be deployed and integrated. Phase 1–2 completion.

### Layer 2: Commercial support contracts (early-to-mid-stage)

Available once the platform has production deployments that organizations depend on. Support contracts require a stable, well-documented platform and a community of operators who are running it in production.

**Prerequisite:** Phase 3–4 completion and initial community adoption.

### Layer 3: Enhanced AI reasoning features (mid-stage)

A commercial API tier that provides access to more powerful AI models, higher rate limits, and multi-model ensemble analysis. This tier is viable once the AI reasoning layer (Phase 5) is implemented and operators understand its value.

**Prerequisite:** Phase 5 completion and operator familiarity with AI reasoning capabilities.

### Layer 4: Managed deployment (mid-to-late-stage)

A hosted offering for organizations that want the capability without the operational burden. This requires operational maturity: robust deployment tooling, monitoring, backup, and customer isolation.

**Prerequisite:** Phase 4–5 completion, operational infrastructure, and demonstrated reliability.

### Layer 5: Enterprise contracts (late-stage)

Multi-site enterprise deployments with SLA-backed support, SSO integration, and role-based access control. Enterprise sales cycles require references, case studies, and a track record of production deployments.

**Prerequisite:** Demonstrated production deployments, community reputation, Phase 5+ capabilities.

### Layer 6: Managed federation coordination (long-term)

A commercial service that manages trust circle membership, verifies participant identities, and provides curated behavioral fingerprint feeds for organizations that want federation benefits without managing peer relationships themselves.

**Prerequisite:** Phase 8 (federation) completion and sufficient network scale to make curated feeds valuable.

---

## Realistic Monetization Timeline

This timeline is tied to the engineering roadmap phases and assumes successful community adoption at each stage. It is not a forecast — it is a sequencing guide.

| Timeframe | Roadmap phase | Commercial readiness |
|---|---|---|
| Now–6 months | Phase 0–1 | Not yet. Focus is building the foundation and community trust. |
| 6–12 months | Phase 2–3 | First consulting engagements possible. No formal products. |
| 12–18 months | Phase 3–4 | Support contracts viable for early production deployments. |
| 18–30 months | Phase 4–5 | Enhanced AI tier becomes viable as AI features mature. |
| 30–48 months | Phase 5–6 | Managed deployment tier viable if adoption has scaled. |
| 48+ months | Phase 6–7 | Enterprise contracts and managed federation viable. |

**The precondition for every stage:** community adoption and community trust. Revenue follows utility and trust; it cannot be pursued ahead of them.

---

## What Sustainable Looks Like

Sustainability for this project does not require a large organization or a venture-funded growth trajectory. It requires:

1. Enough community adoption that the platform is used by operators who provide real-world feedback
2. Enough commercial activity (consulting, support, eventually managed tiers) that core maintainer work can be compensated
3. Enough contributor involvement that the project is not dependent on a single maintainer
4. A license and governance structure that prevents commercial capture without community consensus

A project that runs for ten years on modest sustainable revenue, serves thousands of operators, and contributes to the development of open standards for behavioral threat intelligence is more valuable than a project that raises venture capital, burns fast, and gets acquired by a platform whose interests conflict with its users'.

That is the business model.

---

*Cross-references: [FOUNDING_PRINCIPLES.md](FOUNDING_PRINCIPLES.md) · [OPEN_SOURCE_STRATEGY.md](OPEN_SOURCE_STRATEGY.md) · [VISION.md](VISION.md) · [POSITIONING.md](POSITIONING.md) · [ROADMAP.md](ROADMAP.md)*
