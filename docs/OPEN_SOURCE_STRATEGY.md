# LegionTrap TI — Open Source Strategy

**Document type:** Strategic — open-source philosophy, license rationale, governance, contribution rules
**Audience:** Maintainers, contributors, autonomous agents, strategic decision-makers
**Last reviewed:** 2026-05-23

---

## Why Open Source Is Not Optional Here

For most security tools, open source is a distribution strategy. For LegionTrap, it is the source of the trust that makes adoption possible.

The operators LegionTrap targets — security researchers, privacy-sensitive organizations, sovereign operators, technically sophisticated individuals — do not deploy black-box security tools. They cannot. If the platform handling their attack telemetry is closed source, they have no way to verify that it behaves as claimed. For this segment, closed source is not a minor inconvenience; it is a disqualifying property.

Open source is also the privacy guarantee. An operator who can read the code, run the code locally, inspect the network traffic, and verify that no unexpected connections are made does not need to trust a vendor's privacy policy. They can verify the behavior. Open source is the mechanism by which the sovereignty promise is provable rather than asserted.

Finally, open source is the mechanism by which a project with limited initial resources can build a tool that serves a global audience. A closed product requires that every feature be built by employees of the company that owns it. An open project can receive contributions from every security researcher, every honeypot operator, and every sensor integration developer in the community.

---

## License: AGPL-3.0

### Why AGPL, not MIT or Apache

The AGPL-3.0 (GNU Affero General Public License) is the correct license for LegionTrap for a specific reason: it closes the network use loophole that weaker copyleft licenses leave open.

Under MIT or Apache, a company can take the LegionTrap codebase, run it as a cloud service, and never contribute back. They benefit from the community's work while competing with the open-source project commercially without reciprocal obligation. This is a common pattern: the commercial entity creates a managed offering that competes with the self-hosted version while free-riding on community development.

Under AGPL, if someone provides a network service using the LegionTrap codebase, they must make their modified source code available under AGPL. This does not prevent commercial services — it requires that they contribute back. An organization can run a managed LegionTrap deployment commercially; they cannot keep their enhancements proprietary while using AGPL code.

### What AGPL does not prevent

- Self-hosting and running LegionTrap for your own purposes
- Using LegionTrap in a corporate environment for internal security operations
- Running LegionTrap as a service for clients (with AGPL source disclosure requirements)
- Contributing to the project under a contributor license agreement
- Building integrations and plugins that use the LegionTrap API

### What AGPL requires from commercial users

If you run a service using LegionTrap for others (a managed platform, a hosted offering), you must make the source code of any modifications available under AGPL. This is the reciprocal obligation that makes the license appropriate for a sustainability-minded open-source project.

### AGPL and the commercial tier

A commercial entity associated with this project that runs managed deployments is subject to the same AGPL requirements as any other commercial user. The correct structure for a commercial offering is either: (a) operate under AGPL with full source disclosure, or (b) obtain a commercial license that permits proprietary modifications.

Commercial licenses for entities that require proprietary modifications are a standard and legitimate way for open-source projects to generate revenue. They do not compromise the open-source project — they are a parallel arrangement that allows commercial use at a different obligation level.

---

## Trust Model

### Open source as a verification mechanism

The trust model for LegionTrap is: trust is verified, not assumed. An operator who wants to know whether the platform sends telemetry to external servers, logs sensitive data, or has security vulnerabilities can read the code. The answer is in the code, not in a privacy policy.

This trust model requires that the code be readable, well-structured, and free of obfuscation. Code that is technically open but effectively unreadable provides the legal appearance of openness without the actual verification benefit.

### Community as a bug-finding layer

A security tool that is reviewed only by its creators has far fewer eyes on it than a security tool used by thousands of operators who read its code, instrument its network traffic, and occasionally audit its behavior. The open-source model converts community scale into security review capacity.

This is not a substitute for deliberate security review (see SECURITY_AUDIT.md for the formal audit process). It is an additional layer that no closed-source product can have.

### Transparency about limitations

Open source also requires honesty about what the software does not do. LegionTrap's documentation explicitly distinguishes implemented features from planned features from conceptual directions. The documentation does not overstate the platform's current capabilities. This honesty is part of the trust model.

---

## Community Contribution Philosophy

### What contributions are valuable

- **Bug reports:** Specific, reproducible, with enough detail to diagnose the issue
- **Bug fixes:** Small, focused changes with tests
- **Sensor integrations:** Normalizers for honeypot formats not yet supported
- **Test coverage:** Expanding coverage for critical paths that are under-tested
- **Documentation improvements:** Corrections, clarifications, and additions to existing documents
- **Security reports:** Via responsible disclosure (not public issues for active vulnerabilities)
- **Performance improvements:** With benchmarks demonstrating the improvement
- **Translation and localization:** Making the interface accessible to non-English-speaking operators

### What is not an appropriate contribution in the early stages

- Large feature additions that have not been discussed in an issue first
- Architectural changes that affect core data flows or the schema
- Alternative storage backends (multiple storage backends add maintenance cost without proportional value in the early stages)
- AI model integrations beyond the Claude and Ollama backends that are already planned
- UI redesigns without prior discussion

The early-stage constraint is not permanent. As the project matures and the contributor community grows, the scope of welcome contributions expands. The current constraint reflects the need to maintain architectural coherence before the foundation is stable.

### Contribution process

1. Open an issue describing the problem or improvement before writing significant code
2. Wait for maintainer acknowledgment that the direction is sound
3. Create a branch (never commit directly to main)
4. Write tests for new behavior
5. Ensure the full test suite passes
6. Submit a pull request with a clear description of what changed and why
7. Be prepared for review feedback and iteration

Contributions that skip step 1 for significant changes risk being declined not because they are wrong, but because they conflict with upcoming roadmap work or architectural decisions that are not yet public.

---

## Federation Trust Principles

The federation protocol (see FEDERATION_VISION.md) is a specific application of the broader trust model. Key principles that apply specifically to the open-source nature of federation:

### The protocol is open

The behavioral fingerprint format, the federation API contract, and the cryptographic protocols used for signing and verification are all open and documented. A participating operator can audit what data their deployment shares, verify that received fingerprints are structurally valid before acting on them, and implement their own federation client if they choose.

Closed protocols for intelligence sharing are incompatible with the sovereignty proposition. If an operator cannot verify what they are sharing, they cannot make an informed consent decision.

### No central authority

There is no LegionTrap federation server that operators must connect to. The federation protocol is peer-to-peer. Operators choose their peers. No entity — including any commercial entity associated with this project — is positioned as a required intermediary for federation participation.

### The reference implementation is the specification

The federation protocol is defined by the open-source reference implementation and the specification document. A commercial entity cannot define a proprietary extension to the protocol that creates a dependency on their services. Protocol extensions must be proposed and accepted as open standards.

---

## Privacy Guarantees

### What the platform guarantees

- Event data never leaves the local deployment unless the operator explicitly configures an external AI backend or federation sharing
- Default configuration results in no external connections except those the operator initiates
- The platform does not contain telemetry, analytics collection, or remote logging of any kind
- Privacy masking and anonymization for IOC exports are built into the core and available at all tiers

### What the operator is responsible for

- The security of the infrastructure on which the platform runs
- The configuration of external AI backends (which involve external data transfer)
- The consent process for federation participation
- The security of API keys and credentials that provide access to the platform

The platform provides the tools for secure, sovereign operation. The operator is responsible for using them correctly. Documentation must be clear about both what the platform does and what the operator must do.

---

## Local-First Philosophy

### Local-first is not a positioning choice

Local-first is the architectural constraint from which most other properties of the platform follow. It means:

- The primary data store is local (SQLite, later PostgreSQL on operator infrastructure)
- AI reasoning can be run entirely locally (Ollama backend)
- All intelligence exports are files the operator stores locally
- Federation shares derived abstractions, not raw data, and does not require any central server
- The dashboard runs in the operator's browser against the operator's local API

An architecture that requires an external service for any core function is not local-first; it is local-first-with-asterisk. The goal is no asterisks.

### Local-first and community contribution

The local-first constraint means that contributions that add cloud dependencies to core functionality are not acceptable. A sensor normalization plugin that requires a cloud API call to classify an event, or a UI component that loads assets from an external CDN, violates the local-first property even if it provides genuine value.

Contributions that add optional external integrations (for example, an optional integration with a commercial GeoIP API) are acceptable if they are: clearly documented as optional, disabled by default, and architected so that the platform degrades gracefully when the external service is unavailable.

---

## What Should Never Become Proprietary

The following capabilities are the core intellectual and strategic contribution of the open-source project. They must remain open-source in perpetuity, regardless of commercial developments:

- The event ingestion pipeline and normalization logic
- The behavioral fingerprint schema and extraction algorithms
- The campaign detection and clustering algorithms
- The federation protocol specification and reference implementation
- The privacy masking and anonymization algorithms
- All standard format exporters (STIX, MISP, ATT&CK, Sigma, pf.conf, UFW)
- The AI reasoning architecture (not the specific AI model — the prompting and retrieval patterns)
- The database schema and migration tools

These are the technical expression of the platform's core value proposition. Making any of them proprietary would destroy the basis on which the open-source community was built.

---

## Governance Philosophy

### Decision-making in the early stage

In the early stage of the project (before an established contributor community exists), governance is primarily the responsibility of the founding maintainer. Decisions about architecture, roadmap, license, and contribution acceptance rest with the maintainer.

This is not a long-term governance model — it is an early-stage practicality. Single-maintainer governance is sustainable for a small project and becomes a liability as the project grows.

### Governance as the project matures

As the contributor community grows, governance should evolve to distribute decision-making in ways that are proportional to contribution and expertise. The appropriate evolution path:

**Stage 1 (current):** Single maintainer. All significant decisions made openly (via issues, documentation) with community input welcomed.

**Stage 2 (early community):** Core contributor group with commit access. Architecture decisions made collaboratively among core contributors. Maintainer retains license and project direction authority.

**Stage 3 (established community):** A project foundation or governance committee that includes core contributors. License and architectural decisions require committee consensus. No single person holds veto authority over the project's direction.

**Stage 4 (if commercial scale warrants):** Separation between the open-source project governance and any commercial entity's governance. The commercial entity may fund development but does not control the project.

### What governance must protect

- The AGPL license cannot be changed to a more restrictive or proprietary license without community consensus
- The founding principles cannot be abandoned to serve commercial interests
- Core contributors cannot be excluded from governance without cause
- Commercial entities associated with the project cannot gain veto authority over open-source direction

### The fork right

Any AGPL project can be forked. If the governance of this project degrades in ways that violate the founding principles, the correct response is a fork that continues under the original principles, not an attempt to reclaim control of a project whose governance has been captured.

The open-source license is the final guarantee. No commercial relationship, no governance capture, and no maintainer decision can retroactively revoke the rights granted to people who received the software under AGPL-3.0.

---

## Future Contributor Rules

These rules apply to contributors at all levels, from first-time bug reporters to core maintainers.

### Contributor rules

1. **No contribution may introduce telemetry or external data collection** without explicit operator opt-in, prominent documentation, and clear disclosure in the CHANGELOG.

2. **No contribution may weaken privacy protections** in existing features. Privacy regressions are treated with the same severity as security regressions.

3. **No contribution may create external service dependencies** in core functionality. Optional integrations must be genuinely optional and must degrade gracefully.

4. **No contribution may introduce a backdoor**, intentional or otherwise — including features that allow remote command execution, configuration modification, or data access without explicit operator action.

5. **All contributions must have tests** for new behavior. The test suite is the contract that changes do not break existing behavior.

6. **Security-sensitive changes** (auth, ingestion validation, schema, federation) require maintainer review before merge. No self-approval on security-critical paths.

7. **Documentation must be updated** when behavior changes. A change that is not documented is not complete.

8. **Commit messages must describe why**, not just what. A year from now, the author of a commit may not remember why a decision was made; the commit message is the record.

### Maintainer rules

1. **Maintainers do not merge their own significant changes** without review. For small fixes, self-merge is acceptable; for architecture and security changes, another maintainer or core contributor must review.

2. **Maintainers do not accept contributions that violate the founding principles**, regardless of the contributor's standing or the feature's apparent utility.

3. **Maintainers disclose conflicts of interest** — specifically, when a commercial relationship exists with the person or organization behind a contribution, and when that relationship might influence the acceptance decision.

4. **Maintainers respond to security reports** within 72 hours and coordinate responsible disclosure before public disclosure.

---

*Cross-references: [FOUNDING_PRINCIPLES.md](FOUNDING_PRINCIPLES.md) · [BUSINESS_MODEL.md](BUSINESS_MODEL.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md) · [AUTONOMOUS_OPERATIONS.md](AUTONOMOUS_OPERATIONS.md)*
