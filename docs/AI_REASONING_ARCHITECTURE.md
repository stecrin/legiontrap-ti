# LegionTrap TI — AI Reasoning Architecture

**Document type:** Implementation blueprint — AI context retrieval, prompt design, and reasoning pipeline
**Audience:** Engineers, autonomous agents performing Phase 5+ work
**Last reviewed:** 2026-05-23
**Status:** Design-complete. Describes the system that Phases 5 and 6 implement. Prerequisites: DATABASE_SCHEMA.md (Phase 1), INGESTION_PIPELINE.md (Phase 2), GeoIP enrichment (Phase 3), and event type taxonomy (Phase 4).

---

## Core Design Principle

**The AI does not read raw events. It reads structured summaries derived from SQL queries.**

This is the critical design decision that separates a useful AI analysis layer from an expensive toy. The difference:

| Approach | What the AI receives | Result |
|---|---|---|
| Raw event injection | 10,000 JSON lines | Context window exhaustion; unreliable counting; hallucinated aggregations |
| Structured context | Pre-aggregated SQL summaries | Accurate counts; reliable pattern analysis; grounded, citeable conclusions |

Every AI prompt in this system is built from SQL query results. The AI never sees raw event content. This is not an optimization — it is a correctness requirement.

---

## Prerequisites (AI Stage 0)

These must be complete before any AI feature work begins. See [ROADMAP.md](ROADMAP.md) Phase 1–4 and [AI_ROADMAP.md](AI_ROADMAP.md) Stage 0.

- [ ] SQLite event store (`events` table, Phase 1)
- [ ] `HoneypotEvent` Pydantic schema (Phase 1)
- [ ] GeoIP enrichment on ingestion — `country_code`, `country_name`, `asn`, `asn_org` populated (Phase 3)
- [ ] `event_types` table with ATT&CK taxonomy (Phase 4)
- [ ] `POST /api/ingest` pipeline operational (Phase 2)

Attempting to build the AI layer before these are in place produces a prototype that cannot be evolved into a production capability.

---

## AI Backend Configuration

The AI backend is selected via the `AI_BACKEND` environment variable:

```bash
AI_BACKEND=claude     # Uses Claude API. Event summaries sent to external API.
AI_BACKEND=ollama     # Local inference. No data leaves the system.
AI_BACKEND=none       # AI features disabled. Non-AI functionality unaffected.
```

**When `AI_BACKEND=none`:** All AI-dependent endpoints return:
```json
{"status": "ai_disabled", "message": "AI_BACKEND is set to 'none'. Set AI_BACKEND=claude or AI_BACKEND=ollama to enable AI analysis."}
```
with HTTP 200. Non-AI endpoints continue operating normally.

**When `AI_BACKEND=claude`:** The Claude API is called with structured context. Event summaries are sent externally. Privacy masking rules apply — see the Privacy section below.

**When `AI_BACKEND=ollama`:** A local Ollama instance is called. No data leaves the system. Suitable for air-gapped deployments. Reasoning quality is lower than Claude API for complex analysis.

The backend selection is an operator decision. The code must not hardcode a preference.

---

## The Retrieval-Then-Reason Pattern

All AI analysis follows this pattern:

```
1. Operator query (or scheduled trigger)
         │
         ▼
2. Intent parsing — determine time window, event filters, analysis type
         │
         ▼
3. Context retrieval — run structured SQL aggregation queries
         │
         ▼
4. Context serialization — format query results as structured JSON for the prompt
         │
         ▼
5. Privacy filtering — apply IP masking/hashing if PRIVACY_MODE is active
         │
         ▼
6. Prompt construction — combine context with system instructions and analyst question
         │
         ▼
7. AI model call — send to Claude API or Ollama
         │
         ▼
8. Response parsing — extract summary, key_findings, recommended_actions, confidence
         │
         ▼
9. Citation grounding — verify factual claims are traceable to retrieved data
         │
         ▼
10. Persistence — INSERT INTO ai_analyses
         │
         ▼
11. API response — return structured AIAnalysisResult
```

---

## Context Retrieval Queries

These are the SQL queries that populate the AI context. Each query is named; the context builder calls them by name and assembles their results into the prompt.

### `ctx_event_summary` — overall activity in time window

```sql
SELECT
    COUNT(*)                                     AS total_events,
    COUNT(DISTINCT src_ip)                       AS unique_ips,
    COUNT(DISTINCT asn)                          AS unique_asns,
    COUNT(DISTINCT country_code)                 AS unique_countries,
    MIN(ts)                                      AS window_start,
    MAX(ts)                                      AS window_end
FROM events
WHERE ts BETWEEN :start AND :end;
```

### `ctx_top_event_types` — most common attack types

```sql
SELECT
    event_type,
    et.attack_tactic,
    et.attack_technique,
    COUNT(*)                AS count,
    COUNT(DISTINCT src_ip)  AS unique_ips
FROM events e
LEFT JOIN event_types et ON e.event_type = et.id
WHERE e.ts BETWEEN :start AND :end
GROUP BY e.event_type
ORDER BY count DESC
LIMIT 10;
```

### `ctx_top_asns` — most active attacking ASNs

```sql
SELECT
    asn,
    asn_org,
    country_code,
    COUNT(*)                AS event_count,
    COUNT(DISTINCT src_ip)  AS unique_ips,
    MIN(ts)                 AS first_seen,
    MAX(ts)                 AS last_seen
FROM events
WHERE ts BETWEEN :start AND :end
  AND asn IS NOT NULL
GROUP BY asn
ORDER BY event_count DESC
LIMIT 10;
```

### `ctx_top_countries` — geographic distribution

```sql
SELECT
    country_code,
    country_name,
    COUNT(*)                AS event_count,
    COUNT(DISTINCT src_ip)  AS unique_ips
FROM events
WHERE ts BETWEEN :start AND :end
  AND country_code IS NOT NULL
GROUP BY country_code
ORDER BY event_count DESC
LIMIT 10;
```

### `ctx_timing_distribution` — probe timing patterns (per-hour activity)

```sql
SELECT
    strftime('%H', ts)   AS hour_of_day,
    COUNT(*)             AS event_count
FROM events
WHERE ts BETWEEN :start AND :end
GROUP BY hour_of_day
ORDER BY hour_of_day;
```

### `ctx_new_vs_returning_ips` — repeat attacker detection

```sql
-- IPs seen before the analysis window
WITH prior_ips AS (
    SELECT DISTINCT src_ip FROM events
    WHERE ts < :start AND src_ip IS NOT NULL
),
window_ips AS (
    SELECT DISTINCT src_ip FROM events
    WHERE ts BETWEEN :start AND :end AND src_ip IS NOT NULL
)
SELECT
    COUNT(*) FILTER (WHERE w.src_ip IN (SELECT src_ip FROM prior_ips)) AS returning_ips,
    COUNT(*) FILTER (WHERE w.src_ip NOT IN (SELECT src_ip FROM prior_ips)) AS new_ips,
    COUNT(*) AS total_unique_ips
FROM window_ips w;
```

### `ctx_active_campaigns` — known campaigns in this window (Phase 6+)

```sql
SELECT
    c.id, c.label, c.status,
    c.event_count, c.confidence,
    bf.targeting_category, bf.primary_protocol, bf.timing_type
FROM campaigns c
LEFT JOIN behavioral_fingerprints bf ON c.fingerprint_id = bf.id
WHERE c.status = 'active'
  AND c.last_seen BETWEEN :start AND :end
ORDER BY c.last_seen DESC
LIMIT 5;
```

This query returns `[]` before Phase 6 — the AI context builder handles empty campaign results gracefully.

---

## Prompt Architecture

### System prompt (constant)

```
You are a threat intelligence analyst for a self-hosted honeypot network.
You receive structured attack data and produce accurate, evidence-grounded analysis.

Rules:
- Every factual claim must be traceable to the provided data.
- State uncertainty explicitly when the data is insufficient for a conclusion.
- Never hallucinate IP addresses, ASN names, event counts, or time ranges.
- If asked about something the data does not contain, say so directly.
- Output must be valid JSON matching the schema provided.
```

### Context block (assembled from SQL query results)

```json
{
  "analysis_window": {
    "start": "2026-05-22T00:00:00Z",
    "end": "2026-05-22T23:59:59Z"
  },
  "event_summary": {
    "total_events": 412,
    "unique_ips": 17,
    "unique_asns": 8,
    "unique_countries": 5
  },
  "top_event_types": [
    {"event_type": "auth_failed", "attack_technique": "T1110.001", "count": 387, "unique_ips": 14},
    {"event_type": "port_scan", "attack_technique": "T1046", "count": 25, "unique_ips": 6}
  ],
  "top_asns": [
    {"asn": 12345, "asn_org": "Example ISP", "country_code": "RU", "event_count": 203, "unique_ips": 6},
    {"asn": 67890, "asn_org": "Another Provider", "country_code": "CN", "event_count": 145, "unique_ips": 4}
  ],
  "top_countries": [
    {"country_code": "RU", "country_name": "Russia", "event_count": 203},
    {"country_code": "CN", "country_name": "China", "event_count": 145}
  ],
  "returning_vs_new": {
    "returning_ips": 3,
    "new_ips": 14,
    "total_unique_ips": 17
  },
  "active_campaigns": []
}
```

### Output schema (requested from the model)

```json
{
  "summary": "string — 2-5 sentence narrative summary",
  "key_findings": ["string", "..."],
  "recommended_actions": ["string", "..."],
  "confidence": "low | medium | high",
  "notable_actors": [
    {"asn": 12345, "asn_org": "...", "pattern": "..."}
  ]
}
```

The model is instructed to produce JSON matching this schema. The response is parsed with Pydantic and stored in `ai_analyses`.

---

## Privacy Controls for AI Prompts

When `PRIVACY_MODE=on`, IP addresses in the context block are transformed before being included in the prompt. The same masking logic used in IOC exports (`iocs_pf.py`) applies here.

A separate `AI_PRIVACY_MODE` environment variable (defaulting to the value of `PRIVACY_MODE`) allows independent control:

```bash
PRIVACY_MODE=on          # controls IOC exports
AI_PRIVACY_MODE=on       # controls what reaches external AI APIs (defaults to PRIVACY_MODE)
```

This allows an operator to export unmasked IPs locally but mask them when sending to an external AI API — useful when the AI backend is Claude (external) but IOC exports are consumed locally.

**Masking in context blocks:**
- IP addresses in `top_asns` source IP fields → masked/hashed
- IP addresses in `returning_vs_new` analysis → counts only (no IPs ever appear in aggregate queries)
- ASN numbers and organization names → **never masked** (ASN data is public; masking it degrades AI reasoning quality with no privacy benefit)

**Absolute prohibitions in AI prompts (regardless of privacy settings):**
- `data.password` from any event — attacker-submitted credentials, never included
- `data.username` from any event — attacker-submitted strings
- Any free-text attacker content
- Raw event JSON lines

---

## The `POST /api/analyze` Endpoint

### Request

```http
POST /api/analyze
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "window_hours": 24,
  "window_start": null,
  "window_end": null
}
```

`window_hours` is the convenience parameter. If `window_start` and `window_end` are provided, they take precedence.

### Response

```json
{
  "analysis_id": "uuid",
  "created_at": "2026-05-22T20:00:00Z",
  "window_start": "2026-05-21T20:00:00Z",
  "window_end": "2026-05-22T20:00:00Z",
  "backend": "claude",
  "summary": "17 distinct source IPs were observed over the 24-hour window...",
  "key_findings": [
    "ASN 12345 (Russia) accounted for 49% of all events with 6 distinct source IPs",
    "3 returning IPs from prior observations; 14 new IPs not seen before",
    "All attack activity was SSH credential brute-force (T1110.001) with no port scan precursors"
  ],
  "recommended_actions": [
    "Consider blocking ASN 12345 at the perimeter if SSH exposure is not required from Russia",
    "Review the 3 returning IPs against prior campaign records for attribution"
  ],
  "confidence": "medium"
}
```

### Authentication

`POST /api/analyze` accepts either JWT or API key (`require_jwt_or_api_key`). It is a read + AI call, not an ingest operation. Both auth methods are appropriate.

---

## Query Architecture for Dashboard and Advanced Analysis

### Dashboard stats (after Phase 1 migration)

```sql
-- Single query replaces the full JSONL scan in stats.py
SELECT
    COUNT(*)                                                        AS total_events,
    COUNT(DISTINCT src_ip)                                          AS unique_ips,
    SUM(CASE WHEN ts > datetime('now', '-24 hours') THEN 1 ELSE 0 END) AS last_24h
FROM events;
```

This runs in milliseconds on 1M+ rows with the `idx_events_ts` index.

### Event timeline (trend chart)

```sql
SELECT
    strftime('%Y-%m-%dT%H:00:00', ts) AS hour,
    event_type,
    COUNT(*)                          AS count
FROM events
WHERE ts > datetime('now', :hours_back)
GROUP BY hour, event_type
ORDER BY hour;
```

### Attack sequence reconstruction (per-IP history)

```sql
SELECT e.ts, e.event_type, e.dst_port, e.protocol,
       et.attack_tactic, et.attack_technique,
       s.asn_org, s.country_name
FROM events e
LEFT JOIN event_types et ON e.event_type = et.id
LEFT JOIN source_ips  s  ON e.src_ip = s.ip
WHERE e.src_ip = :ip
ORDER BY e.ts;
```

### Repeated attacker detection

```sql
SELECT
    src_ip,
    COUNT(*)                          AS total_events,
    COUNT(DISTINCT DATE(ts))          AS active_days,
    MIN(ts)                           AS first_seen,
    MAX(ts)                           AS last_seen,
    asn_org,
    country_name
FROM events e
JOIN source_ips s ON e.src_ip = s.ip
WHERE src_ip IS NOT NULL
GROUP BY src_ip
HAVING active_days > 1
ORDER BY total_events DESC
LIMIT 20;
```

### GeoIP / ASN correlation

```sql
SELECT
    asn,
    asn_org,
    country_code,
    COUNT(*)                AS event_count,
    COUNT(DISTINCT src_ip)  AS unique_ips,
    MIN(ts)                 AS first_seen,
    MAX(ts)                 AS last_seen
FROM events
WHERE ts > datetime('now', '-7 days')
  AND asn IS NOT NULL
GROUP BY asn
ORDER BY event_count DESC
LIMIT 20;
```

### Campaign recognition query (Phase 6+)

```sql
SELECT
    c.id, c.label, c.status, c.confidence,
    c.first_seen, c.last_seen, c.event_count,
    bf.targeting_category, bf.primary_protocol,
    bf.timing_type, bf.timing_interval_ms
FROM campaigns c
LEFT JOIN behavioral_fingerprints bf ON c.fingerprint_id = bf.id
WHERE c.status IN ('active', 'dormant')
ORDER BY c.last_seen DESC;
```

### Federation fingerprint matching (Phase 7+)

```sql
SELECT
    ff.fingerprint_id,
    ff.contributor_id,
    ff.confidence,
    ff.dimensions_json,
    ff.received_at,
    ff.trust_tier
FROM federation_fingerprints ff
WHERE ff.confidence > 0.7
  AND ff.received_at > datetime('now', '-30 days')
ORDER BY ff.confidence DESC;
```

---

## AI Limitations and Risk Mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated event counts | Context block contains pre-computed exact counts from SQL. Model is instructed counts are authoritative. |
| Hallucinated IP addresses | IPs are never in the context unless the operator explicitly requests per-IP analysis. |
| Prompt injection via event data | Event content (usernames, passwords, User-Agent strings) is never included in prompts. Only typed, structured aggregations appear. |
| Model downtime blocking core functionality | AI endpoints return `503` when AI backend is unavailable. All non-AI endpoints continue working. |
| Privacy leak via AI output | AI output is not cached or forwarded without the same privacy filtering applied to context input. |
| Over-confident conclusions | System prompt instructs explicit uncertainty disclosure. Output schema includes `confidence` field. UI must display confidence level alongside narrative. |
| Stale analysis | `created_at` is stored and returned. Analysis results are never presented as "live" — they are a snapshot of a specific time window. |

---

## Behavioral Memory Integration (Phase 6+)

When behavioral fingerprints and campaign clusters exist, the AI context expands to include:

1. **Campaign context:** Active and recently-dormant campaigns with their behavioral signatures
2. **Fingerprint similarity:** Whether new events match known fingerprints from prior campaigns
3. **Historical narrative:** "This ASN was previously associated with campaign C-2025-089 in November 2025"

The AI receives this as an additional context block:

```json
{
  "known_campaigns": [
    {
      "id": "C-2025-089",
      "label": "SSH scanner from AS12345",
      "status": "dormant",
      "last_seen": "2025-11-15",
      "targeting_category": "credential-brute-force",
      "timing_type": "periodic",
      "timing_interval_ms": 2000
    }
  ],
  "fingerprint_matches": [
    {
      "current_pattern": "periodic SSH, 2000ms interval",
      "matched_campaign": "C-2025-089",
      "match_confidence": 0.87,
      "matched_dimensions": ["timing_type", "timing_interval_ms", "primary_protocol"]
    }
  ]
}
```

This is the mechanism that produces the "returning actor" detection capability: the AI can state "The timing pattern observed today matches campaign C-2025-089 from 6 months ago, with 87% confidence across 3 behavioral dimensions."

---

## Implementation File Map

```
app/
  routers/
    analyze.py              # POST /api/analyze endpoint
  services/
    ai_context.py           # context retrieval — runs SQL queries, assembles context dict
    ai_prompt.py            # prompt construction — system prompt + context → final prompt
    ai_backends.py          # Claude API and Ollama client wrappers
    ai_privacy.py           # privacy filtering for AI context (IP masking)
  models/
    ai.py                   # AIAnalysisResult, IngestRequest Pydantic models
  db/
    repository.py           # all SQL including the context retrieval queries above
```

No AI logic belongs in routers. Routers call services. Services call repository. Repository calls SQL.

---

## Testing Requirements

Before Phase 5 is complete:

| Test | Assertion |
|---|---|
| `test_analyze_returns_disabled_when_backend_none` | `AI_BACKEND=none` → 200 with `status: ai_disabled` |
| `test_context_retrieval_queries_are_accurate` | Insert known events, run context queries, assert exact counts |
| `test_privacy_filtering_masks_ips` | `PRIVACY_MODE=on` → no raw IPs in context block |
| `test_password_not_in_ai_context` | Ingest Cowrie event with password, build context, assert no password in output |
| `test_analyze_stores_result_in_db` | POST /api/analyze → ai_analyses table has one row |
| `test_analyze_window_parameters` | `window_hours=24` and explicit `window_start/end` produce equivalent results |
| `test_analyze_empty_window` | Analysis window with zero events returns graceful summary, not error |

AI backend integration tests (calling the real Claude API or Ollama) are skipped in CI unless `AI_BACKEND` is explicitly set. They run only in manual verification environments.

---

*Cross-references: [AI_ROADMAP.md](AI_ROADMAP.md) · [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) · [BEHAVIORAL_INTELLIGENCE.md](BEHAVIORAL_INTELLIGENCE.md) · [ROADMAP.md](ROADMAP.md)*
