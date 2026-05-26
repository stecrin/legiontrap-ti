# LegionTrap TI — Phase 5 Architecture Blueprint

**Document type:** Pre-implementation architecture blueprint
**Status:** Implemented — see [PHASE_5_CLOSEOUT.md](PHASE_5_CLOSEOUT.md) for delivery record and deferred items
**Audience:** Engineers, contributors
**Date:** 2026-05-26

---

## 1. Phase 5 Mission

Phase 4 gave the system behavioral memory: every observed IP has a fingerprint, similar fingerprints are grouped into campaigns, and campaigns carry lifecycle state. The system can answer *who is doing this* with a deterministic, auditable answer.

Phase 5 answers a different question: **what does it mean?**

The gap between structured campaign data and operator-useful intelligence is the gap between a database record and a sentence. An operator staring at a `confidence: 0.82` score and a `reactivation_count: 2` needs to understand: this is a known actor who went quiet for three months and is back with new infrastructure. That interpretation is what Phase 5 delivers.

Phase 5 has two distinct parts and they must be delivered in order:

**Part A — Operational maturity.** Three tasks that should have been in Phase 4 but were explicitly deferred: the campaign lifecycle management job (automatic status transitions), the campaign analytics population job (`attack_tactic_dist`, `top_target_ports`), and configurable similarity weights. These are prerequisite infrastructure for meaningful AI analysis. AI summarizing stale campaign states or empty analytics fields produces less useful output.

**Part B — AI-assisted campaign intelligence.** A single, tightly scoped AI layer that reads structured campaign and fingerprint data and produces natural-language summaries and threat briefs. The AI layer is additive: the system must function fully without it, and every AI output must be traceable to specific deterministic records.

Phase 5 does not deliver autonomous responses, alerting pipelines, or conversational interfaces. Those are Phase 6 and Phase 7 territory.

---

## 2. What AI Is Allowed to Do

These are the only permitted AI operations in Phase 5:

| Operation | Input | Output |
|---|---|---|
| Summarize a single campaign | Campaign record + fingerprint features + recent observations | Natural-language paragraph describing behavioral characteristics and lifecycle |
| Generate a multi-campaign threat brief | Set of campaign records for a time window | Structured narrative brief with per-campaign summaries and cross-campaign observations |
| Describe fingerprint dimensions | Behavioral fingerprint feature dict | Plain-language explanation of what the features indicate (e.g., "probe interval of 2s is consistent with automated tooling") |
| Surface similarity context | Similarity score + per-dimension breakdown | Sentence explaining which behavioral dimensions matched and at what weight |

All four operations are **read-only** and **output-only**. They consume structured data already in the database and return text. No side effects.

---

## 3. What AI Must Never Do

These restrictions are absolute. They may not be relaxed in any PR under Phase 5.

| Prohibition | Reason |
|---|---|
| Decide campaign membership | Campaign assignments are deterministic and auditable; AI-assigned memberships are neither |
| Execute any database write | The AI layer is a read-only consumer; it never modifies system state |
| Call external targets or APIs | No outbound requests other than the configured AI backend |
| Run on the ingest path | LLM latency must never block event ingestion; the two paths are strictly separated |
| Trigger alerts or notifications | Phase 5 has no autonomous alerting; AI conclusions require operator review |
| Block, rate-limit, or firewall any IP | Active response is explicitly out of scope for all Phase 5 work |
| Claim certainty about attribution | AI-generated attribution must be framed as hypothesis, not assertion |
| Consume raw event records directly | AI context is limited to pre-aggregated fingerprints and campaign summaries; raw event tables are never passed to prompts |
| Override a deterministic similarity score | The score is computed by `app/intelligence/clustering.py`; AI may describe it but not replace it |

---

## 4. Data Inputs AI May Consume

The AI layer may only consume these pre-aggregated data structures. Raw event rows, raw IP tables, and full audit logs are not permitted AI inputs.

### Permitted inputs

**Campaign record** (from `campaigns` table):
- `id`, `name`, `status`, `confidence`
- `first_seen`, `last_seen`, `dormant_since`, `reactivation_count`
- `member_ip_count`, `attack_tactic_dist`, `top_target_ports`
- `notes` (explainability JSON from clustering)

**Behavioral fingerprint** (from `behavioral_fingerprints` table):
- `timing_features`, `sequence_features`, `protocol_features`
- `credential_features`, `target_features`
- `confidence`, `fingerprint_version`
- Raw IP value is excluded from AI context; only features pass through

**Campaign observations** (from `campaign_observations` table):
- `observed_at`, `event_count`, `is_reactivation`, `dormancy_gap_days`, `notes`
- Source IP is excluded from AI context

**Campaign members** (aggregated counts only):
- Member count, date range of member activity
- Individual member IPs are never passed to AI context

**Time-window aggregates** (pre-computed before prompt construction):
- Total events, distinct source IP count, top event types by count
- Top target ports by count, top ASN names by count
- No individual IPs appear in these aggregates

### Explicitly prohibited inputs

- Raw `events` or `raw_events` table rows
- Individual source IP addresses (masked or unmasked)
- `audit_log` rows
- `behavioral_fingerprints.source_ip` field
- Any data from `source_ips` table beyond aggregated counts

---

## 5. Privacy Boundaries

The Phase 4 privacy model (IOC export layer, PRIVACY_MODE flag, HMAC masking) extends to the AI layer with additional constraints.

### When PRIVACY_MODE is off

- Campaign and fingerprint features may be passed to the AI backend
- Individual IPs are excluded from AI context regardless of PRIVACY_MODE setting
- AI summaries may reference ASN names and event type names
- AI summaries may not embed raw IP addresses; prompt construction must strip them

### When PRIVACY_MODE is on

- AI backend calls that involve external API (Claude API) are blocked; the endpoint returns `HTTP 422` with a clear explanation
- Local AI backend (Ollama) may operate in PRIVACY_MODE because no data leaves the system
- The setting `AI_BACKEND=ollama` with `PRIVACY_MODE=on` is a supported configuration

### Prompt construction rule

All prompt construction functions must be tested against a corpus of representative data to verify that no raw IP addresses appear in the constructed prompt string. This is enforced by a prompt-validation test utility (see Section 11).

### Data sent to external AI API

When `AI_BACKEND=claude`:
- Only the pre-aggregated structures listed in Section 4 are included in the prompt
- No full event content, no credentials, no raw IPs
- All external API calls are logged to `audit_log` with the timestamp, the endpoint called, and the byte count of the payload (not the content)

---

## 6. Local vs Cloud AI Strategy

The AI backend is configurable via environment variable. The system must behave correctly in all three modes.

```
AI_BACKEND=claude    # Claude API (default); structured campaign data sent externally
AI_BACKEND=ollama    # Local inference via Ollama; no data leaves the system
AI_BACKEND=none      # AI features disabled; all non-AI functionality unaffected
```

### Claude API (cloud)

- Model: `claude-haiku-4-5-20251001` for campaign summaries (fast, sufficient for structured → prose tasks)
- Model: `claude-sonnet-4-6` for multi-campaign threat briefs (better cross-campaign synthesis)
- API key: `ANTHROPIC_API_KEY` environment variable; startup raises `ValueError` if `AI_BACKEND=claude` and key is unset
- Request timeout: 30 seconds; retry once on timeout; return degraded response on second failure
- Rate limiting: operator-configurable `AI_MAX_REQUESTS_PER_MINUTE` (default: 10)

### Ollama (local)

- Default model: `llama3.2` (3B parameter variant for constrained hardware)
- Endpoint: `OLLAMA_HOST` environment variable (default: `http://localhost:11434`)
- Suitable for air-gapped deployments; lower synthesis quality on complex cross-campaign analysis
- Startup does not fail if Ollama is unavailable; the AI endpoint returns `HTTP 503` with `"AI_BACKEND=ollama but Ollama is unreachable"`

### None (disabled)

- All `/api/analyze/*` endpoints return `HTTP 503` with `{"detail": "AI features are disabled. Set AI_BACKEND=claude or AI_BACKEND=ollama to enable."}`
- No import errors, no startup failures
- All non-AI endpoints are completely unaffected

### Backend abstraction

A single `app/ai/backend.py` module provides the `generate(prompt: str) -> str` interface. Both Claude and Ollama implementations live behind this interface. The router never calls an AI SDK directly; it always calls `generate()`. This ensures that adding or swapping backends never touches router code.

---

## 7. Prompt and Output Structure

### Structured facts first, AI prose second

All prompt construction follows this invariant: the structured data record is assembled into a validated Python dict before any string formatting touches it. The dict is serialized to a readable text block that forms the prompt's `<data>` section. The AI is instructed to summarize this data, not to reason beyond it.

### Campaign summary prompt shape

```
You are a threat intelligence analyst assistant. Summarize the following
campaign record in 2-4 sentences for an operator brief. State what the
campaign does, its current status, and any notable recurrence behavior.
Do not infer or hypothesize beyond the data provided.
If the data is insufficient for a conclusion, say so explicitly.

<data>
Campaign: {name}
Status: {status}
Confidence: {confidence_pct}%
First observed: {first_seen}
Last observed: {last_seen}
Member IP count: {member_ip_count}
Reactivation count: {reactivation_count}
{dormancy_block if dormant_since else ""}
Behavioral dimensions:
  Timing: {timing_summary}
  Sequence: {sequence_summary}
  Protocol: {protocol_summary}
  Credential: {credential_summary}
  Target: {target_summary}
Recent observations: {observation_count} in last {window_days} days
</data>

Respond in plain prose. Do not use bullet points. 2-4 sentences only.
```

### Multi-campaign brief prompt shape

```
You are a threat intelligence analyst assistant. The following campaigns
were active in the specified time window. Write a threat brief of 3-6
sentences covering: the most significant campaign, any shared behavioral
patterns across campaigns, and any notable changes in actor behavior.
Do not infer beyond the data provided.

<window>
{start_ts} — {end_ts}
Total events: {event_count}
Distinct source IP count: {ip_count} (IPs not disclosed)
</window>

<campaigns>
{per_campaign_summary_block}
</campaigns>

Respond in plain prose. One paragraph maximum. Label any uncertain
interpretation with "possible" or "may indicate".
```

### Output schema

All AI endpoints return a consistent JSON envelope:

```json
{
  "ai_assisted": true,
  "ai_backend": "claude|ollama",
  "model": "claude-haiku-4-5-20251001",
  "generated_at": "2026-05-26T12:00:00Z",
  "warning": "This analysis is AI-assisted. All factual claims are derived from deterministic campaign data. Attribution language is inferential, not asserted.",
  "content": "<AI-generated prose>",
  "source_records": {
    "campaign_ids": ["<id>", ...],
    "fingerprint_ids": ["<source_ip_hash>", ...],
    "observation_count": 12
  }
}
```

The `ai_assisted: true` flag and `warning` field are mandatory. They must appear on every response regardless of backend or mode. The frontend must render the warning label visibly — not in a tooltip, not collapsed.

---

## 8. Human Approval Model

Phase 5 implements a **display-and-label** approval model. There is no workflow step where an operator approves an AI output before it is shown. Instead, every AI output is visibly labelled as AI-assisted, and the underlying deterministic evidence is always shown alongside it.

The UI must follow this layout invariant:

```
[Campaign: SWIFT-JACKAL-14]  [active]  [confidence: 82%]

Deterministic summary (always visible):
  First seen: 2026-01-15    Last seen: 2026-05-24
  Members: 7 IPs            Reactivation count: 2
  Dimensions: timing ████ sequence ████ protocol ██

┌──────────────────────────────────────────────────────────────┐
│ ⚠ AI-assisted analysis — not an asserted attribution         │
│                                                              │
│ [Generate summary]  [Dismiss]                                │
│                                                              │
│ (summary appears here after generation)                      │
└──────────────────────────────────────────────────────────────┘
```

Key rules:
- The AI summary is never shown by default; it requires an explicit operator action ("Generate summary")
- The deterministic data panel is always visible and always shown before the AI panel
- The AI warning label is not optional and not dismissible
- AI outputs are never cached and re-shown as if they are current; each display is regenerated or shown with a timestamp
- There is no workflow where an operator "approves" an AI output to trigger an automated downstream action — AI outputs are read-only intelligence

---

## 9. Failure Modes and Hallucination Controls

### Structural grounding

Every prompt includes only named fields from the verified data structures in Section 4. There are no free-text fields in Phase 5 campaign data that could carry injected instructions. The `notes` JSON field in `campaign_observations` contains only the explainability dict produced by `clustering.py` (numeric scores and decision labels); it is serialized as structured data in the prompt, never interpolated as a narrative fragment.

### Prompt injection defense

The `notes` field and any string field that originates from external observation (e.g., `campaign.name`) is sanitized before prompt inclusion:
- Truncated to a configurable max length (default: 200 chars per field)
- Scanned for instruction-like patterns (`ignore previous`, `disregard`, `system:`, `<|`, etc.)
- If a field fails the scan, it is replaced with `[FIELD REDACTED — failed safety check]` in the prompt

### Output validation

After generation, the AI output is validated before being returned:
- Maximum length check: 1,000 chars for campaign summary, 2,500 chars for multi-campaign brief
- IP address pattern check: any string matching an IPv4 or IPv6 pattern in the output causes the response to be rejected and replaced with a degraded fallback (`"AI output rejected — contained potential IP address data. Use the structured data panel."`)
- Refusal detection: if the model declines to answer, the response wrapper returns `"content": null` and `"refused": true` rather than surfacing the model's refusal text to the operator

### Hallucination controls

Phase 5 takes a structural, not a probabilistic, approach to hallucination:

1. **No open-ended questions.** Prompts never ask "what do you think about this actor?" They ask for summaries of specific provided data. The model is constrained to prose-ify what it is given.

2. **Uncertainty language requirement.** The prompt explicitly instructs the model to use "possible", "may indicate", or "data insufficient for conclusion" when it cannot ground a statement in the provided data.

3. **No external knowledge instruction.** Prompts include the explicit instruction: "Do not use information outside the provided data. Do not reference threat actor names, APT groups, or external threat intelligence databases."

4. **Short output limits.** Short outputs are less likely to drift into unsupported claims. The 2-4 sentence and one-paragraph limits serve both UX and hallucination control goals.

5. **Source record citation.** Every response includes `source_records` with the specific campaign IDs and observation counts used. If an operator reports a suspicious claim in an AI output, the source records provide the audit path.

### Degraded mode behavior

| Failure condition | Response |
|---|---|
| AI backend unreachable | `HTTP 503` with structured error; deterministic data panel unaffected |
| AI backend timeout (after retry) | `HTTP 504` with `"content": null` and `"timed_out": true` |
| Output rejected (IP in response) | `HTTP 200` with `"content": null` and `"rejected": true` and reason |
| Output too long | Truncated to limit; `"truncated": true` flag added |
| `AI_BACKEND=none` | `HTTP 503` with feature-disabled message |
| `PRIVACY_MODE=on` + `AI_BACKEND=claude` | `HTTP 422` with privacy conflict explanation |

All failure modes return valid JSON. The frontend must handle every case without crashing.

---

## 10. PR Sequencing

Phase 5 is eight PRs in two groups. Group A is operational maturity and must merge before Group B begins.

### Group A — Operational Maturity (no AI)

**PR 1 — Campaign lifecycle management job**

Scheduled job that runs daily (configurable via `LIFECYCLE_JOB_INTERVAL_HOURS`). Transitions:
- `active` → `dormant` when `last_seen < now - CAMPAIGN_DORMANT_DAYS` (default: 90)
- `dormant` → `historical` when `last_seen < now - CAMPAIGN_HISTORICAL_DAYS` (default: 365)

Implemented as a FastAPI startup background task (not an external cron). Operator can trigger manually via `POST /api/admin/run-lifecycle-job` (API key only, not JWT).

Tests: unit tests for the transition logic, integration tests for the job execution, tests verifying that campaigns below the threshold are not transitioned.

**PR 2 — Campaign analytics population**

A repository method and companion job that computes `attack_tactic_dist` and `top_target_ports` for each campaign by joining `campaign_members` → `events` → `event_types`.

`attack_tactic_dist`: JSON dict of `{tactic_name: event_count}` for all events attributed to campaign members.
`top_target_ports`: JSON array of `[{port: N, count: M}]` top-5 by event count.

Job runs after the lifecycle job on the same schedule. Results populate the existing nullable columns; no schema change required.

Tests: integration tests verifying correct aggregation from fixture events.

**PR 3 — Configurable similarity weights**

Move the hardcoded similarity weights (timing 20%, sequence 35%, protocol 25%, credential 10%, target 10%) to `app/core/config.py` as `SIMILARITY_WEIGHT_*` environment variables with the current values as defaults.

No behavior change when defaults are used; existing tests continue to pass. Adds tests verifying that non-default weights are used correctly.

### Group B — AI Integration

**PR 4 — AI backend abstraction and safety infrastructure**

New module `app/ai/backend.py`:
- `AIBackend` abstract base with `generate(prompt: str) -> str`
- `ClaudeBackend` (uses `anthropic` SDK)
- `OllamaBackend` (uses `httpx` to call Ollama REST API)
- `DisabledBackend` (raises `AIDisabledError`)
- Factory function `get_ai_backend() -> AIBackend` that reads `AI_BACKEND` setting

New module `app/ai/prompt_builder.py`:
- `build_campaign_summary_prompt(campaign: dict, fingerprint: dict, observations: list[dict]) -> str`
- `build_threat_brief_prompt(campaigns: list[dict], window_start: str, window_end: str) -> str`
- `sanitize_field(value: str, max_len: int) -> str` — truncation + injection pattern scan
- `validate_ai_output(text: str) -> tuple[str | None, str | None]` — returns `(validated_text, rejection_reason)`

New settings: `AI_BACKEND`, `ANTHROPIC_API_KEY`, `OLLAMA_HOST`, `AI_MAX_REQUESTS_PER_MINUTE`, `CAMPAIGN_DORMANT_DAYS`, `CAMPAIGN_HISTORICAL_DAYS`.

Tests: unit tests for prompt builder (field sanitization, injection pattern detection, IP presence in output), unit tests for each backend stub.

**PR 5 — Single campaign AI summary endpoint**

`POST /api/analyze/campaign/{campaign_id}`

- Auth: `require_jwt_or_api_key`
- Fetches campaign, fingerprint (for most-recent member), and last 10 observations
- Builds prompt via `prompt_builder`
- Calls `get_ai_backend().generate()`
- Returns the standard AI output envelope

No request body required. The campaign ID in the path is the only parameter.

Response time budget: 30s hard timeout. The endpoint is synchronous in Phase 5; async is Phase 6.

Tests: integration tests using a mocked `AIBackend` (not a live API call); tests for all failure modes from Section 9; test verifying that `ai_assisted: true` is always present; test verifying that the response contains `source_records`.

**PR 6 — Campaign summary dashboard integration**

Adds a "Generate AI Summary" button to the `CampaignDetail` expanded row in `Campaigns.jsx`. The button is only shown when `AI_BACKEND !== 'none'` (determined by a new `GET /api/analyze/status` endpoint that returns `{"ai_enabled": bool, "ai_backend": str}`).

On click: POST to `/api/analyze/campaign/{id}`, show loading state, render result with warning label. The deterministic data panel remains visible; the AI panel appears below it with the warning banner.

On error or rejection: show a non-alarming message ("AI summary unavailable") without surfacing error details to the operator.

**PR 7 — Multi-campaign threat brief endpoint**

`POST /api/analyze/brief`

Request body:
```json
{
  "window_start": "2026-05-01T00:00:00Z",
  "window_end": "2026-05-26T23:59:59Z",
  "max_campaigns": 10
}
```

Fetches campaigns active in the window (by `last_seen` range), pre-computes window aggregates, builds brief prompt, returns the standard envelope.

`max_campaigns` caps the campaigns included in a single prompt (default: 10, max: 25). Campaigns are sorted by `last_seen DESC` before truncation.

Tests: integration tests with mocked backend; test verifying `max_campaigns` cap; test verifying that no IPs appear in the generated prompt.

**PR 8 — Phase 5 documentation and close-out**

- `docs/PHASE_5_CLOSEOUT.md`
- Update `docs/ROADMAP.md` to mark Phase 5 complete
- Update `docs/ARCHITECTURE.md` with `app/ai/` module map
- Update `docs/PHASE_5_BLUEPRINT.md` status to Implemented

---

## 11. Testing Strategy

### Unit tests

Location: `tests/unit/`

| Test file | Coverage |
|---|---|
| `test_prompt_builder.py` | Field sanitization; injection pattern detection; IP-in-output rejection; prompt length limits; each prompt template produces expected sections |
| `test_ai_backend.py` | Backend factory selects correct implementation; DisabledBackend raises AIDisabledError; ClaudeBackend uses correct model names; OllamaBackend constructs correct request |
| `test_lifecycle_job.py` | Transition logic: active → dormant threshold; dormant → historical threshold; campaigns at threshold boundary; campaigns below threshold not transitioned |
| `test_analytics_job.py` | `attack_tactic_dist` correct aggregation; `top_target_ports` top-5 ordering; campaigns with no events produce empty/null fields |

### Integration tests

Location: `tests/integration/`

| Test file | Coverage |
|---|---|
| `test_analyze_endpoints.py` | `POST /api/analyze/campaign/{id}` — 200 with mocked backend; 404 on missing campaign; 503 with disabled backend; 422 on PRIVACY_MODE + cloud backend; `ai_assisted: true` always present; `source_records` always present; output rejected when mock returns IP address |
| `test_brief_endpoint.py` | `POST /api/analyze/brief` — 200; `max_campaigns` cap enforced; empty window returns graceful response; no IPs in constructed prompt |
| `test_lifecycle_integration.py` | Job correctly transitions campaigns in the test DB; `POST /api/admin/run-lifecycle-job` requires API key; repeated job runs are idempotent |

### Prompt injection test

A dedicated test utility in `tests/conftest.py` or a separate `tests/unit/test_prompt_safety.py`:
- Constructs a campaign record where every string field contains a prompt injection attempt
- Verifies that `build_campaign_summary_prompt()` produces a prompt that passes the injection scan
- Verifies that the constructed prompt contains no raw IP-like strings from the fixture data

### No live API calls in tests

The `AIBackend` abstraction exists specifically so that integration tests can inject a `MockAIBackend` that returns a controlled string. No test may call a live Claude API or a live Ollama endpoint. The `ANTHROPIC_API_KEY` must not be required for the test suite to pass.

---

## 12. Anti-Complexity Rules

These rules exist to prevent Phase 5 from drifting into the territory of Phase 6 or Phase 7 during implementation. They are not suggestions; they are scope boundaries.

| Rule | Rationale |
|---|---|
| One AI endpoint per PR | Scope creep in AI features compounds; keep each PR reviewable in isolation |
| No streaming responses | Streaming requires async infrastructure changes that belong in Phase 6 |
| No conversation history / multi-turn | Stateful conversations require session management; out of scope for Phase 5 |
| No AI-generated Sigma rules | Sigma generation is PR 7 of Phase 5; it does not involve AI prose — it is a template expansion over behavioral data |
| No webhook or async notification | Alerting infrastructure is Phase 6 |
| No vector database | Semantic similarity search is not required for campaign summary generation |
| No fine-tuning or model training | Phase 5 uses foundation models only; no training data collection |
| No operator-editable prompts | Custom prompt templates are a Phase 6 configuration feature; hardcoded prompts are safer and auditable |
| No AI involvement in clustering | `app/intelligence/clustering.py` is immutable from Phase 5's perspective |
| No new database tables | All Phase 5 data uses existing columns (`attack_tactic_dist`, `top_target_ports`) or is transient (AI outputs are not persisted) |
| Backend abstraction only, not pluggable at runtime | `AI_BACKEND` is read at startup; hot-swapping backends during a session is not supported |

---

## Deferred to Phase 6

These items are valid and anticipated but explicitly out of Phase 5 scope:

- Async AI analysis (non-blocking endpoint with job queue)
- AI output persistence and history
- Conversational analyst interface (multi-turn Q&A)
- Automated alerting triggered by AI analysis
- Operator-editable AI prompt templates
- Webhook delivery of AI-generated briefs
- Federation-aware AI analysis (cross-deployment fingerprint comparison)
- Configurable per-deployment similarity weights beyond environment variables

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [PHASE_4_CLOSEOUT.md](PHASE_4_CLOSEOUT.md) · [AI_ROADMAP.md](AI_ROADMAP.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
