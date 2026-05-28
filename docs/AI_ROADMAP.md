# LegionTrap TI — AI Integration Roadmap

**Document type:** AI capabilities planning and architecture
**Audience:** Engineers, autonomous agents, contributors
**Last reviewed:** 2026-05-22

---

## Guiding Principle

AI integration in LegionTrap is not decorative. Every AI feature must produce intelligence that is more accurate, more explainable, or more actionable than what a human analyst could produce from the same data in the same time. If a feature does not meet this bar, it should not be built.

AI integration also has a prerequisite: **the data must be structured and queryable before AI can reason over it.** LLM prompting over unstructured JSONL scans produces unreliable results. The Phase 1 storage migration (see [ROADMAP.md](ROADMAP.md)) is the prerequisite for all AI features described here.

---

## Stage 0 — Prerequisites (Must Complete First)

Before any AI integration:

- [ ] SQLite event store (ROADMAP.md Phase 1)
- [ ] `HoneypotEvent` Pydantic schema with typed fields (ROADMAP.md Phase 1)
- [ ] GeoIP enrichment on ingestion (country, ASN) (ROADMAP.md Phase 3)
- [ ] Event type taxonomy defined (ROADMAP.md Phase 4)

Attempting AI integration without these produces a prototype that cannot be evolved into production capability.

---

## Stage 1 — Minimal Viable AI Reasoning

**Goal:** Prove the concept. A single endpoint that produces a useful natural-language intelligence brief from real, structured event data.

### `POST /api/analyze`

Accepts: time window or event filter parameters
Returns: structured JSON containing narrative brief, key findings, and recommended actions

**Implementation approach:**
1. Query the event store for the requested time window
2. Aggregate: top source ASNs, top event types, timing distribution, new vs. returning IPs
3. Construct a structured prompt with the aggregated data
4. Call Claude API (or local LLM) with the structured data
5. Return the model's analysis as the API response

**Example output:**
```json
{
  "window": "2026-05-22T00:00:00Z / 2026-05-22T23:59:59Z",
  "summary": "17 distinct sources observed. Three coordinated SSH brute-force
              campaigns identified from ASN 12345 (RU), ASN 67890 (CN), and
              ASN 11111 (BR). The ASN 12345 campaign shows timing consistent
              with automated tooling (2-second probe intervals). One new actor
              (185.x.x.x) used an unusual port sequence not observed in the
              previous 30 days.",
  "key_findings": [...],
  "recommended_actions": [...],
  "confidence": "medium"
}
```

**Model options:**
- **Claude API** (default): Best reasoning quality; requires API key; data leaves local infra
- **Ollama + Llama 3** (local): Runs entirely on local hardware; no data leaves the system; suitable for air-gapped deployments; lower reasoning quality on complex analysis

The model backend must be configurable via environment variable (`AI_BACKEND=claude|ollama|none`).

---

## Stage 2 — Behavioral Analysis and Campaign Detection

**Goal:** Move from event-level analysis to campaign-level intelligence. Identify that multiple individual events are part of the same coordinated actor behavior.

### Behavioral Fingerprint Engine

A behavioral fingerprint encodes how an actor behaves, not what infrastructure they use. Components:

- **Port sequence:** The ordered sequence of ports probed
- **Timing distribution:** Inter-probe intervals and daily/weekly patterns
- **Tool signature:** Patterns in User-Agent strings, banner grabbing behavior, protocol quirks
- **Targeting pattern:** Which of the operator's services and ports are targeted
- **Geographic/ASN envelope:** The ASN and geography envelope of the campaign's infrastructure

A fingerprint is stored as a structured record in the database. Each incoming event is compared against known fingerprints to identify campaign membership.

### Campaign Cluster Model

Events that share multiple fingerprint dimensions are grouped into campaign clusters. A cluster represents a coordinated actor or operation. Clusters are assigned:
- A persistent ID
- A confidence score (how coherent is the behavioral cluster)
- A timeline (first seen, last seen, event count)
- An actor label (system-assigned initially, analyst-editable)

### AI-Assisted Cluster Analysis

Once clusters are formed, AI reasoning provides:
- Natural language description of the campaign's behavioral characteristics
- Comparison against previously seen campaigns ("this cluster shares 3 behavioral dimensions with cluster C-2025-047")
- Suggested ATT&CK technique mapping based on observed behaviors
- Confidence assessment of attribution hypotheses

---

## Stage 3 — Memory Systems

**Goal:** Persistent behavioral memory that survives across operator sessions, infrastructure rotations, and long time gaps.

This is the strategic core of the AI layer. Memory is what transforms LegionTrap from an analysis tool into an intelligence asset.

### Event Memory (Already implicit in storage)

Every ingested event is retained indefinitely (subject to configurable retention policy). The event store is the raw memory layer.

### Campaign Memory

Campaign clusters are persistent records. A campaign that was last observed 6 months ago is not deleted — it is marked as dormant. When an event arrives that matches a dormant campaign's behavioral fingerprint, the campaign is reactivated and the operator is alerted.

This is the "returning actor" detection capability. It requires:
- Persistent campaign records with behavioral fingerprints
- A fingerprint-matching function that runs on every new event (or batch)
- A dormancy and reactivation state machine

### Actor Hypothesis Memory

Over time, the system builds hypotheses about threat actors — groups of campaigns that appear to originate from the same organization or infrastructure ecosystem. Hypotheses are:
- AI-generated (based on behavioral similarity across campaigns)
- Analyst-editable (operators can confirm, deny, or modify hypothesis labels)
- Revisable (new evidence updates the hypothesis)

Actor hypotheses are explicitly probabilistic. The system does not claim certainty about attribution; it reports confidence levels and the evidence supporting each hypothesis.

### Contextual Memory for AI Reasoning

When an operator asks a question ("have we seen this ASN before?"), the AI reasoning layer has access to:
- The full historical event record
- All campaign cluster records
- All actor hypotheses
- All previous AI-generated analyses

This contextual memory is what makes the reasoning useful rather than generic. Without it, the AI answers about this event in isolation. With it, the AI answers about this event in the context of everything the system has observed.

---

## Stage 4 — Natural Language Analyst Interface

**Goal:** Conversational Q&A interface over the operator's behavioral event database.

This is not a chatbot. It is an analyst interface — a precise tool for querying intelligence.

### Example interactions:

```
Operator: "What is the most active campaign in the last 7 days?"
System:   "Campaign C-2026-031 is the most active: 847 events across 14 source IPs
           from ASN 12345 (Russia), using SSH brute-force with 2-second probe intervals.
           This campaign was also observed in November 2025 (C-2025-089) with the same
           timing pattern. The infrastructure has been completely rotated since then."

Operator: "Have any of today's IPs appeared before?"
System:   "3 of today's 12 source IPs have appeared in previous observations:
           - 185.x.x.x: last seen 2026-03-15, campaign C-2026-019
           - 91.x.x.x: last seen 2025-11-02, campaign C-2025-089
           - 104.x.x.x: new actor with no prior observations"

Operator: "Generate a Sigma rule for the port 22 brute-force pattern from this week."
System:   [returns formatted Sigma rule based on observed behavioral characteristics]
```

### Implementation approach:

1. Natural language query is parsed for intent and parameters
2. Relevant data is retrieved from the event and campaign stores
3. Retrieved data is formatted as structured context for the AI model
4. Model generates response grounded in the retrieved data
5. Response is returned with source citations (which events, which campaigns)

The AI must never hallucinate intelligence. All factual claims must be traceable to specific events or campaign records. The system should explicitly state when a question cannot be answered from available data.

---

## Stage 5 — Autonomous Monitoring and Alerting

**Goal:** The system proactively identifies significant events and notifies the operator without requiring manual queries.

### Alert types:

| Alert | Trigger | Delivery |
|---|---|---|
| Returning campaign | Known campaign fingerprint matches new events | Webhook, email, Telegram |
| Novel behavioral pattern | Event cluster with no historical match | Webhook |
| Campaign escalation | Significant increase in event rate for known campaign | Webhook |
| New actor from known ASN | Source ASN previously associated with malicious activity | Webhook |
| Threshold breach | Event rate exceeds configurable threshold | Webhook |

### Autonomous monitoring loop:

```
Every N minutes:
  1. Run behavioral fingerprint matching on recent events
  2. Update campaign cluster records
  3. Check alert rules against updated campaign state
  4. For each triggered alert: generate AI brief, dispatch notification
  5. Log alert and brief to alert history
```

This is a background task, not a synchronous API operation. It must not block the API and must degrade gracefully if AI reasoning is unavailable.

---

## Stage 6 — Multi-Agent Analysis Pipeline (Long-Term)

**Goal:** Specialized AI agents operating as a coordinated pipeline for complex threat analysis.

This stage requires the federation layer (Phase 8 of main roadmap) to be meaningful at scale. It is a long-term architectural direction, not a near-term implementation plan.

### Agent roles in the pipeline:

| Agent | Responsibility |
|---|---|
| Ingestion Agent | Validates, normalizes, and enriches incoming events |
| Correlation Agent | Identifies behavioral patterns and campaign clusters |
| Enrichment Agent | Queries external sources (OSINT, reputation) while respecting privacy policy |
| Attribution Agent | Builds and updates actor hypotheses |
| Narrative Agent | Produces natural-language intelligence briefs |
| Alert Agent | Monitors for significant state changes and dispatches notifications |
| Report Agent | Generates structured incident reports from campaign analysis |

### Orchestration:

A supervisor agent coordinates the specialist agents. Agents communicate through structured message passing (not shared mutable state). Each agent has defined input and output schemas. The supervisor can spawn, halt, and query specialist agents.

This architecture maps directly to the Claude Agents API multi-agent pattern. The LegionTrap agent system would be built on this foundation.

---

## AI Privacy Considerations

**Data handling with external AI APIs:**

When using an external AI API (Claude, OpenAI), event data must be treated with the same privacy controls as any other external data transfer.

- **Never send raw IPs to external AI APIs** when privacy mode is enabled
- **Apply the same anonymization** (masking or hashing) to AI prompt data that would apply to IOC exports
- **Log all external AI API calls** with timestamps and data volumes (not data content) for operator audit
- **Provide a fully local AI option** (Ollama) for operators who cannot accept any external data transfer

The AI backend configuration should be explicit and operator-visible:

```bash
AI_BACKEND=claude          # Uses Claude API; event summaries sent externally
AI_BACKEND=ollama          # Local inference; no data leaves the system
AI_BACKEND=none            # AI features disabled; manual analysis only
```

**When AI_BACKEND=none**, all AI-dependent endpoints should return a clear status rather than an error, and all non-AI functionality should operate normally.

---

## AI Limitations and Risks

| Risk | Mitigation |
|---|---|
| Hallucinated intelligence | Ground all AI outputs in cited event data; never allow unsupported factual claims |
| Model-dependent reasoning quality | Provide multiple backend options; test each with representative data |
| Prompt injection via event data | Sanitize event content before inclusion in prompts; use structured (not string-interpolated) prompt construction |
| Over-reliance on AI conclusions | UI should always show the underlying evidence alongside AI conclusions |
| AI downtime affecting core functionality | AI features are always additive; the non-AI core must function when AI is unavailable |
| Bias in behavioral attribution | Attribution hypotheses are explicitly probabilistic; operators can override; no automated blocking based on AI attribution alone |
| Data exfiltration via AI prompt | Clearly log what data is sent to external APIs; provide local-only mode |

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [BEHAVIORAL_INTELLIGENCE.md](BEHAVIORAL_INTELLIGENCE.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md) · [ARCHITECTURE.md](ARCHITECTURE.md)*
