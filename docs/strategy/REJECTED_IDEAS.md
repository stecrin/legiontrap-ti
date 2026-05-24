# LegionTrap TI — Rejected Ideas Log

**Document type:** Append-only anti-pattern preservation
**Audience:** Founders, maintainers, future contributors, autonomous agents
**Last reviewed:** 2026-05-23
**Governance:** Entries are appended when ideas are rejected at any stage. Existing entries are never deleted or modified. If circumstances change and an idea is reconsidered, a new entry is added referencing the original.

---

## Purpose

This document preserves ideas that were considered and rejected. Its purpose is not to criticize those ideas — many of them were reasonable in some context. Its purpose is to prevent the project from cycling through the same territory repeatedly.

An idea in this document is not permanently dead. Each entry includes a "What Would Need to Change" section that defines the conditions under which the idea could be reconsidered. Absent those conditions, the rejection stands.

Before proposing a direction that might have been evaluated before, read this document. If the idea is here, understand why it was rejected before proposing it again.

---

## Entry Format

```
### RI-NNN: [Title]
**Date rejected:** YYYY-MM-DD
**Stage at rejection:** Brainstorming / Candidate Insight / Validated Insight
**Decision reference:** SD-NNN (if a formal decision was made)
**The idea:** What was proposed
**Why rejected:** The reasoning that led to rejection
**What would need to change:** Conditions under which this could be reconsidered
```

---

## Entries

### RI-001: Centralized Federation Server
**Date rejected:** 2025-11-15
**Stage at rejection:** Candidate Insight
**Decision reference:** SD-008
**The idea:** A central server (operated by the project or a commercial entity) collects behavioral fingerprints from all participating deployments, deduplicates and aggregates them, and provides a query API. Operators configure their deployment to push fingerprints to the central server and pull enriched intelligence from it.
**Why rejected:** A centralized model creates a single entity with visibility into the behavioral patterns of all participating operators. This entity — even if operated by well-intentioned project maintainers — can correlate participant identities, infer deployment profiles, and potentially be compelled by legal processes to disclose participant data. More fundamentally, it converts a sovereignty tool into a dependency on the entity operating the server. If that entity changes its policies, raises prices, or shuts down, all federation participants are affected. This is the exact architecture the platform is designed to avoid.
**What would need to change:** If zero-knowledge proofs or equivalent cryptographic primitives made it impossible for the central server to learn anything about individual contributors while still providing meaningful aggregation, a centralized model with those guarantees could be reconsidered. This is a long-term cryptographic research direction, not a near-term possibility.

---

### RI-002: MIT License
**Date rejected:** 2025-11-01
**Stage at rejection:** Candidate Insight
**Decision reference:** SD-007
**The idea:** License under MIT for maximum permissiveness and adoption. Let anyone do anything with the code.
**Why rejected:** MIT allows a commercial entity to take the LegionTrap codebase, run it as a managed service, and contribute nothing back. This is the HashiCorp / Terraform pattern, the MongoDB pattern, the Elasticsearch pattern — open source projects that built community value and then had that value extracted by well-funded commercial entities who could afford to undercut the original project on price while enjoying the ecosystem the community built. AGPL's network-use clause prevents this without preventing legitimate self-hosted or commercial use.
**What would need to change:** If the project determined that community adoption required MIT permissiveness and that the commercial free-riding risk was acceptable, MIT could be reconsidered. This would require evidence that AGPL is substantially harming adoption in the target segment — which is a technically sophisticated segment with generally positive views of copyleft licensing.

---

### RI-003: Cloud-First SaaS Architecture
**Date rejected:** 2025-10-01
**Stage at rejection:** Brainstorming
**Decision reference:** SD-001
**The idea:** Build LegionTrap as a cloud-hosted SaaS. Operators send their events to LegionTrap's cloud platform, get enriched intelligence back, and pay a subscription.
**Why rejected:** This architecture is indistinguishable from the privacy-extractive commercial model the platform is explicitly designed to be the alternative to. The value proposition "sovereign intelligence on your infrastructure" cannot coexist with "send your telemetry to our servers." The target segment would not adopt a cloud-dependent platform regardless of its intelligence quality. Additionally, cloud SaaS requires infrastructure investment, multi-tenant isolation, uptime SLAs, and data handling compliance before the platform provides value — a significantly higher upfront cost.
**What would need to change:** If a distinct market segment emerged that wanted managed security intelligence but was not concerned with sovereignty (perhaps small businesses with no IT staff), a separate cloud offering could be considered. This would be a separate product from the core platform, not a replacement for it.

---

### RI-004: VC Funding Path
**Date rejected:** 2025-11-01
**Stage at rejection:** Brainstorming
**The idea:** Raise venture capital to accelerate development, hire engineers, and capture market share before competitors.
**Why rejected:** VC funding creates misaligned incentives for a sovereignty-focused open-source project. VC investors require growth targets that are incompatible with the "trust first, revenue second" philosophy. The most reliable path to VC exit is acquisition by a large platform — which would likely result in the acquired platform becoming cloud-dependent, closed, or data-extractive. The segment this platform serves is specifically defined by distrust of exactly the corporate structures that VC exit events produce. More fundamentally, the competitive moat (behavioral memory, community trust, federation network effects) requires time, not capital — a well-funded competitor cannot purchase the behavioral history that continuous operation builds.
**What would need to change:** If a VC firm existed that genuinely understood and committed to the sovereignty architecture, the open-source licensing, and the trust model — and had a track record of portfolio companies that maintained these properties post-investment — this could be reconsidered. This is a hypothetical; no such track record exists in the current market.

---

### RI-005: Bundling Honeypot Software with the Platform
**Date rejected:** 2025-10-01
**Stage at rejection:** Brainstorming
**The idea:** Build or bundle a honeypot (SSH, HTTP) directly into LegionTrap, so operators have a single install that does both collection and intelligence.
**Why rejected:** Honeypot software (Cowrie, Dionaea, T-Pot) is well-built and actively maintained by dedicated teams. Building a competing honeypot would duplicate effort that the community has already invested, and would result in a lower-quality honeypot than the dedicated tools. LegionTrap's value is in the intelligence layer above the data collection layer, not in the data collection layer itself. The correct architecture is a clean API (POST /api/ingest) that any honeypot can call, plus integration documentation for the major honeypots. Bundling reduces this to a single-vendor stack.
**What would need to change:** If a significant portion of target operators lack the technical capability to configure a separate honeypot and a separate intelligence platform, a bundled "quickstart" distribution (Docker Compose including a Cowrie container) could provide a simpler path to adoption without requiring LegionTrap to maintain honeypot software. This is different from building a honeypot; it is packaging existing software together.

---

### RI-006: Enterprise Compliance as Primary Focus
**Date rejected:** 2025-10-01
**Stage at rejection:** Brainstorming
**The idea:** Position LegionTrap as an enterprise compliance tool — SOC 2 audit trail generation, HIPAA logging, PCI DSS event correlation.
**Why rejected:** This is the existing market for Splunk, QRadar, Sentinel, and LogRhythm. Competing on compliance reporting requires deep integration with enterprise infrastructure stacks (Active Directory, AWS CloudTrail, Azure) that are outside LegionTrap's scope. Enterprise compliance buyers have 6–18 month procurement cycles, require formal vendor assessments, and expect commercial support SLAs that require significant organizational investment to provide. Most importantly, compliance theater (appearing secure for auditors) and genuine intelligence (understanding the threat landscape) are different goals, and optimizing for the first degrades the second. See FOUNDING_PRINCIPLES.md.
**What would need to change:** If the platform reaches Phase 4–5 maturity and an enterprise compliance use case emerges naturally from operators who are using it for genuine intelligence and also need compliance exports, adding compliance export formats would be appropriate. This is additive, not a primary focus shift.

---

### RI-007: Agent-Based Deployment (XDR Model)
**Date rejected:** 2025-10-01
**Stage at rejection:** Brainstorming
**The idea:** Deploy lightweight agents on monitored systems to collect telemetry, similar to how CrowdStrike Falcon or SentinelOne work.
**Why rejected:** LegionTrap is designed to analyze attack behavior against honeypots and exposed services — the attack surface before internal systems are reached. Agent-based deployment is appropriate for detecting lateral movement, privilege escalation, and post-compromise behavior on managed endpoints. These are different problem domains. An agent on a honeypot provides no additional value beyond what the honeypot already captures. An agent on production systems would be a significant scope expansion into the EDR/XDR market, which is heavily competed and would require massive engineering investment.
**What would need to change:** Nothing in the near-to-medium term. Potentially relevant if LegionTrap ever expands scope from external-facing honeypot intelligence to internal network monitoring — a major strategic pivot that would require a separate product decision.

---

### RI-008: Real-Time IP Blocking Based on AI Analysis
**Date rejected:** 2026-05-22
**Stage at rejection:** Candidate Insight
**The idea:** When the AI reasoning layer identifies a high-confidence malicious IP or campaign, automatically push block rules to the operator's firewall without requiring human approval.
**Why rejected:** Automated blocking based on AI analysis creates unacceptable false-positive risk. An AI-generated false positive that blocks a legitimate IP — an internal monitoring system, a CDN exit node, a health-check service — can cause outages that are worse than the threat being blocked. The platform's AI philosophy explicitly states that AI conclusions must inform human decisions, not replace them. Automated blocking requires a level of AI confidence that cannot be justified in the current state of the art. The platform must suggest; the operator must decide.
**What would need to change:** If AI confidence in behavioral fingerprinting reaches a level where false positive rates are demonstrably below a defined threshold (e.g., < 0.1% FPR on a validated test set), and if operators are given the option to explicitly enable automated blocking for specific rule types with well-defined confidence thresholds, a limited automated blocking feature could be reconsidered. It must remain opt-in, never the default, and limited to well-characterized rule types.

---

### RI-009: PostgreSQL as Initial Storage Backend
**Date rejected:** 2025-10-15
**Stage at rejection:** Candidate Insight
**Decision reference:** SD-003
**The idea:** Start with PostgreSQL directly instead of going through a SQLite phase.
**Why rejected:** PostgreSQL requires running a separate database server process. For the primary deployment target — a homelab operator, a researcher, a self-hosted single-user deployment — this is a significant additional operational burden. Docker Compose can make it easier, but it adds another container, networking configuration, and backup procedure. SQLite's operational simplicity (a single file; backup = copy) directly matches the deployment target. The schema is designed to be PostgreSQL-compatible from day one, so migration is structurally straightforward when it becomes necessary.
**What would need to change:** If the primary deployment target shifts to multi-user, multi-sensor, or high-volume deployments where SQLite's write concurrency limits are a problem, PostgreSQL as the initial backend becomes appropriate. In the current phase, it adds complexity without adding value.

---

### RI-010: IOC Feed as Core Intelligence Product
**Date rejected:** 2025-10-01
**Stage at rejection:** Brainstorming
**Decision reference:** SD-002
**The idea:** The primary intelligence output is an IP blacklist and IOC feed that operators can pull into their firewalls and SIEM.
**Why rejected:** IOC feeds are a commodity. AbuseIPDB, Feodo Tracker, AlienVault OTX, Spamhaus, and dozens of other services provide IP reputation data for free or at minimal cost. Building another IOC feed adds no strategic value and competes in a market with established players and no structural moat. IOC exports (pf.conf, UFW) are implemented as a practical tool for operators who want to immediately block observed attackers — but they are a convenience feature, not the strategic direction. See BEHAVIORAL_INTELLIGENCE.md for the reasoning on why behavioral intelligence supersedes IOCs.
**What would need to change:** Nothing. IOC exports remain appropriate as a practical output format (they exist today). Positioning them as the core product would require abandoning the behavioral intelligence thesis entirely.

---

### RI-011: Managed Threat Intelligence Feed (Commercial)
**Date rejected:** 2025-11-01
**Stage at rejection:** Brainstorming
**The idea:** Aggregate behavioral fingerprints from all LegionTrap deployments (including free self-hosted deployments) into a commercial threat intelligence feed sold to enterprises.
**Why rejected:** This is the exact commercial model the platform's architecture is designed to prevent. It would require collecting event data or behavioral fingerprints from self-hosted deployments without those operators' awareness or consent, converting free users' data into a commercial product. This violates the consent model, the sovereignty philosophy, and the AGPL license's intent. It would also destroy community trust permanently when discovered. Any commercial intelligence product must use only data that operators have explicitly and knowingly contributed to a commercial tier.
**What would need to change:** Nothing. The consent model is non-negotiable. A commercial intelligence product built on explicitly consented contributions from paid tier operators is acceptable; one built on harvested self-hosted deployment data is not.

---

*Entries are appended; never modified or deleted. A rejected idea reconsidered requires a new entry referencing the original.*

*Cross-references: [STRATEGIC_DECISIONS.md](STRATEGIC_DECISIONS.md) · [docs/FOUNDING_PRINCIPLES.md](../FOUNDING_PRINCIPLES.md) · [docs/OPEN_SOURCE_STRATEGY.md](../OPEN_SOURCE_STRATEGY.md)*
