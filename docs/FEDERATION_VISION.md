# LegionTrap TI — Federation Vision

**Document type:** Long-term strategic design — privacy-preserving intelligence sharing
**Audience:** Engineers, strategic planners, autonomous agents, contributors
**Last reviewed:** 2026-05-22

---

## The Strategic Premise

A single operator's behavioral attack memory is valuable. The collective behavioral memory of a thousand operators is transformative.

Federation is the mechanism by which individual deployments contribute to and benefit from shared intelligence without sacrificing the privacy and sovereignty that define the LegionTrap value proposition. It is not optional to the long-term vision — it is the mechanism by which LegionTrap becomes more valuable than any enterprise product that cannot achieve federated intelligence at this privacy level.

The key insight: **you do not need to share raw events to share intelligence**. Behavioral fingerprints are derived, compressed, and privacy-safe representations of attack patterns. Sharing them gives other operators the benefit of your observation history without exposing your infrastructure, your users, or the content of attacks against you.

---

## What Federation Is Not

Before defining what federation is, it is important to define what it is not:

**Not a commercial feed:** Federation is not a business model where a central vendor aggregates participant telemetry and sells it back. There is no central broker. No participant's data flows to a vendor.

**Not IOC sharing:** Federation does not share IP addresses, file hashes, or other ephemeral indicators that expire within hours. IOC sharing already exists (VirusTotal, OTX, AbuseIPDB). LegionTrap federation shares behavioral patterns that remain valid across infrastructure rotation.

**Not mandatory:** Federation is opt-in at every level. An operator can run LegionTrap in fully isolated mode indefinitely. Federation is an enhancement, not a dependency.

**Not a surveillance system:** The federation protocol is designed to prevent any participant from inferring another participant's deployment topology, exposure profile, or operational context from shared fingerprints.

---

## The Behavioral Fingerprint as the Unit of Federation

The behavioral fingerprint (see [BEHAVIORAL_INTELLIGENCE.md](BEHAVIORAL_INTELLIGENCE.md)) is the unit of exchange in the federation protocol. A fingerprint encodes:

- Port sequence patterns (not specific ports, but sequence structure)
- Timing distribution parameters (not raw timestamps, but statistical shape)
- Protocol behavior dimensions (not raw content, but structural characteristics)
- Targeting envelope (normalized to categories, not specific services)
- ASN-level geographic envelope (not individual IPs)

**What a fingerprint deliberately omits:**

- Source IP addresses (never included)
- Destination IP addresses or hostnames (never included)
- Raw event content (never included)
- Session payloads or credentials submitted by attackers (never included)
- Operator identity or deployment context (never included)
- Event timestamps at higher than daily resolution (prevents activity correlation)

A recipient of a behavioral fingerprint cannot determine who observed it, where they are, or what infrastructure they operate. They can only determine: "this behavioral pattern has been observed somewhere in the trust network."

---

## Trust Architecture

### The Consent Model

Federation operates on explicit bilateral consent. An operator must:
1. Generate a federation identity (public/private key pair)
2. Explicitly configure peer relationships (one-way or mutual)
3. Explicitly select which behavioral categories to share and receive
4. Accept the fingerprint data format and validation rules

There is no automatic enrollment. No telemetry is ever transmitted without operator configuration that enables it.

### Trust Tiers

**Tier 0 — Isolated:** No federation. All behavioral memory is local-only. Default for new deployments.

**Tier 1 — Receive-only:** Operator subscribes to one or more trusted feeds of behavioral fingerprints. No local fingerprints are transmitted. Operator benefits from others' observations without contributing.

**Tier 2 — Mutual peer exchange:** Two operators agree to exchange behavioral fingerprints. Each receives the other's observations in return for contributing their own.

**Tier 3 — Trust circle:** A defined group of operators (e.g., an industry sector, a research consortium) establishes mutual exchange relationships. Each member receives aggregated intelligence from all members.

**Tier 4 — Public contribution (long-term):** A public behavioral fingerprint commons, analogous to abuse databases, where any operator can contribute anonymized fingerprints and any operator can receive them. This is the long-term vision; it requires cryptographic privacy guarantees beyond what Tier 0–3 require.

### Identity and Signing

Each participating deployment has:
- A persistent public/private key pair (generated at deployment time)
- A pseudonymous deployment identifier (hash of public key; not linkable to operator identity)
- The ability to sign contributed fingerprints with their private key

Signed fingerprints can be verified for integrity. They cannot be attributed to the signing operator without access to a mapping between deployment identifiers and real-world identities — a mapping that the federation protocol does not maintain.

---

## Privacy-Preserving Federation Protocol

### Transport

Initial implementation: HTTPS REST API between peer deployments.
- `POST /api/federation/contribute` — submit a fingerprint to a peer
- `GET /api/federation/fingerprints` — retrieve fingerprints from a peer (paginated, since-timestamp)
- `GET /api/federation/status` — peer health and metadata

The REST model is simple to implement and audit. The long-term architecture may evolve toward a gossip protocol for decentralized propagation, but REST is the correct starting point.

### Fingerprint Format

```json
{
  "fingerprint_id": "fp-<sha256-of-behavioral-data>",
  "schema_version": "1.0",
  "observed_at": "2026-05-22T00:00:00Z",
  "contributor_id": "deploy-<hash-of-public-key>",
  "signature": "<base64-ed25519-signature>",
  "dimensions": {
    "port_sequence_class": "sequential-ascending",
    "timing_distribution": {"type": "periodic", "interval_ms": 2000, "jitter_pct": 5},
    "protocol": "SSH",
    "protocol_variant": "OpenSSH-compatible",
    "targeting_category": "credential-brute-force",
    "asn_geography": ["RU", "UA", "BY"],
    "campaign_duration_class": "sustained"
  },
  "confidence": 0.87,
  "event_count": 412
}
```

**What is NOT in the format:**
- Source IPs
- Destination IPs
- Raw event data
- Operator location or identity
- Precise timestamps

### Validation

Received fingerprints are validated before storage:
1. Schema version compatibility check
2. Signature verification against contributor's known public key
3. Field range validation (confidence 0–1, event_count positive, etc.)
4. Behavioral plausibility check (reject fingerprints with impossible dimension combinations)

Invalid fingerprints are rejected and logged. They are not stored or acted upon.

---

## Intelligence Value of Federation

### Collective Campaign Recognition

When a campaign has been observed and fingerprinted by one operator, all federated peers receive the fingerprint. If the same campaign subsequently probes a peer's infrastructure, the peer's system immediately recognizes it as a known campaign — not a novel actor.

This dramatically expands each operator's effective observational history. An operator who has been running for 3 months benefits from the behavioral memory of peers who have been running for 3 years.

### Early Warning

A campaign targeting one operator may be the leading edge of a broader campaign targeting many operators. When the first-hit operator contributes a fingerprint immediately after observing the campaign, federated peers are warned before they are targeted.

This transforms the federation from a retrospective intelligence resource into a prospective early-warning system.

### Attribution Confidence

A behavioral pattern observed by one operator is interesting. The same pattern observed independently by ten operators in different sectors and geographies is a high-confidence indicator of a coordinated campaign. Federation enables cross-operator attribution confidence that no single operator could achieve alone.

### Rare Attack Detection

Some highly targeted attacks are too rare to appear in any single operator's history. An operator who is specifically targeted by a sophisticated nation-state actor may have only a handful of events from that actor. In isolation, these events look like noise. Aggregated across multiple targeted operators who independently observe similar behavioral patterns, the pattern becomes detectable.

---

## Privacy Attack Analysis

Any federation design must analyze the privacy attacks it enables or prevents.

### Attack: Inferring operator deployment from fingerprint content

**Threat:** A malicious federation peer analyzes received fingerprints to infer which services the contributing operator runs (by observing which targeting categories they contribute fingerprints for).

**Mitigation:** Targeting categories are normalized to broad classes (SSH, HTTP, database, IoT). Specific service names, ports, or application versions are not included. A fingerprint for SSH brute-force targeting reveals that the operator runs an SSH-exposed service — which is intentional (honeypots expose services by design).

### Attack: Correlating fingerprints to identify individual operators

**Threat:** A malicious peer collects fingerprints over time and uses statistical patterns in contribution timing to identify which deployment contributed which fingerprints.

**Mitigation:** Fingerprints include only daily-resolution timestamps. Contribution batching (rather than real-time submission) further reduces timing correlation. Deployment identifiers are pseudonymous. No fingerprint contains content unique to a single operator's infrastructure.

### Attack: Poisoning the federation with false fingerprints

**Threat:** A malicious peer contributes fingerprints for behavioral patterns that don't exist, causing false campaign detections at recipient deployments.

**Mitigation:** Fingerprint signatures allow recipients to verify integrity. Confidence scores reflect the quality of the contributing observation. Recipient systems apply plausibility filtering. Operators can configure trusted peer lists and exclude untrusted contributors.

### Attack: Deanonymizing operators via ASN/geography fields

**Threat:** If only one operator in a trust circle is in a specific country, fingerprints with that country's ASN can be attributed to them.

**Mitigation:** ASN geography fields use regional aggregates (e.g., "EU-West") rather than specific countries when contributor anonymity requires it. Operators with unique exposure profiles can omit geography dimensions.

---

## Federation and the Regulatory Environment

Federation is designed to be compatible with the regulatory constraints that define the sovereign operator segment:

**GDPR:** Behavioral fingerprints do not contain personal data (no IPs, no user-attributable data). Sharing fingerprints across EU borders does not trigger GDPR Article 46 cross-border transfer requirements.

**Data residency requirements:** Each operator stores their own event data locally. Only derived fingerprints cross deployment boundaries. Operators subject to data residency requirements can participate in federation without violating them.

**Air-gapped environments:** For deployments that cannot connect to any external network, Tier 0 (isolated) mode provides full local functionality. Federation is explicitly optional.

---

## Decentralized vs. Centralized Federation Models

### Centralized model (not chosen)

A central server collects fingerprints from all participants and provides a query API. This is operationally simple but:
- Creates a single point of failure
- Creates a single point of surveillance (the operator of the central server)
- Creates a single point of commercial capture
- Is incompatible with the sovereign operator philosophy

### Federated peer-to-peer model (chosen)

Operators maintain direct peer relationships. Each deployment is a node in the network. There is no central server. Intelligence propagates through peer-to-peer exchange.

### Gossip protocol (long-term)

For large trust circles, a gossip protocol (similar to how distributed databases synchronize state) enables fingerprint propagation without each operator needing to maintain N explicit peer connections. A fingerprint contributed by one node propagates through the network within a configurable number of hops.

Gossip protocol implementation is a Phase 8+ concern. The initial implementation uses explicit peer configuration.

---

## Federation Roadmap

### Stage 0: Specification

- Finalize fingerprint format (schema v1.0)
- Define REST API contract
- Define signing and verification protocol
- Write protocol specification document

### Stage 1: Local Implementation

- Implement fingerprint extraction from behavioral clusters (requires Phase 6 of main roadmap)
- Implement local fingerprint store
- Implement fingerprint matching against locally stored fingerprints

### Stage 2: Bilateral Exchange

- Implement `POST /api/federation/contribute` and `GET /api/federation/fingerprints` endpoints
- Implement peer configuration (trusted peers list, API key exchange)
- Implement signature generation and verification
- Test bilateral exchange between two local deployments

### Stage 3: Trust Circle Support

- Implement multi-peer configuration
- Implement fingerprint deduplication across multiple sources
- Implement confidence aggregation (same fingerprint from multiple sources → higher confidence)
- Document trust circle setup process

### Stage 4: Public Commons (Long-Term)

- Evaluate and implement advanced privacy guarantees (differential privacy, zero-knowledge proofs) for public contribution
- Design public directory of federation endpoints
- Implement rate limiting and anti-abuse controls for public endpoints

---

## Relationship to Commercial Threat Intelligence

The federation model does not compete with commercial threat intelligence platforms — it complements them and addresses a gap they cannot fill.

Commercial platforms provide:
- Global-scale IOC aggregation
- Threat actor profiles maintained by dedicated teams
- Historical incident attribution

Federation provides:
- Behavioral patterns that survive IOC rotation
- Intelligence specific to your attack surface
- Intelligence you can trust because you know its provenance
- Intelligence you can share without surrendering it to a commercial entity

An operator who uses both gets the best of both worlds. LegionTrap does not require operators to choose between federated behavioral intelligence and commercial IOC feeds — it integrates with MISP and STIX (see [ROADMAP.md](ROADMAP.md)) to allow both.

---

*Cross-references: [BEHAVIORAL_INTELLIGENCE.md](BEHAVIORAL_INTELLIGENCE.md) · [AI_ROADMAP.md](AI_ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) · [POSITIONING.md](POSITIONING.md)*
