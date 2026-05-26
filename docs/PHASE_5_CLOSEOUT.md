# Phase 5 Close-Out — First AI Integration

**Document type:** Phase completion record and architectural handoff
**Audience:** Engineers, contributors
**Date:** 2026-05-26

---

## What Phase 5 Delivered

Phase 5 moved the platform from passive behavioral recognition to active intelligence interpretation. The central question Phase 5 answers is: *what does this campaign mean, in plain language, to the operator running this system?*

Phase 5 was delivered in two groups. Group A closed three operational maturity gaps left deferred from Phase 4. Group B added the AI reasoning layer on top of the now-complete campaign data model.

### Pull Requests

| PR | Branch | Title |
|----|--------|-------|
| #42 | `feat/phase5-campaign-lifecycle` | Campaign lifecycle maintenance job |
| #43 | `feat/phase5-campaign-analytics-config` | Campaign analytics population and configurable thresholds |
| #44 | `feat/phase5-ai-backend-abstraction` | AI backend abstraction layer |
| #45 | `feat/phase5-prompt-builder-safety` | Prompt builder and AI safety layer |
| #46 | `feat/phase5-campaign-summary-endpoint` | Single campaign AI summary endpoint |
| #47 | `feat/phase5-dashboard-ai-panel` | Dashboard AI summary panel |
| #48 | `feat/phase5-multi-campaign-brief` | Multi-campaign threat brief endpoint |
| #49 | `docs/phase5-closeout` | Phase 5 documentation and close-out |

---

### Group A — Operational Maturity

**Campaign lifecycle management (PR #42)**

A background job that runs on a configurable interval (`LIFECYCLE_JOB_INTERVAL_HOURS`, default: 24h) to apply deterministic lifecycle transitions:
- `active` → `dormant` when `last_seen < now - CAMPAIGN_DORMANT_DAYS` (default: 90 days)
- `dormant` → `historical` when `last_seen < now - CAMPAIGN_HISTORICAL_DAYS` (default: 365 days)
- `dormant` or `historical` → `reactivated` when a new matching fingerprint is observed

The job is implemented as a FastAPI startup background task, not an external cron. An operator can trigger a manual run via `POST /api/admin/run-lifecycle-job` (API key only). Transitions are idempotent; re-running the job on an already-transitioned campaign produces no change.

**Campaign analytics population (PR #43)**

A companion job computes two analytics columns for each campaign by joining `campaign_members → events → event_types`:
- `attack_tactic_dist`: JSON dict of `{tactic_name: event_count}` for all events attributed to campaign members
- `top_target_ports`: JSON array of `[{port: N, count: M}]`, top-5 by event count

Both columns were already defined in the Phase 4 schema as nullable. The analytics job populates them on first run and refreshes them on subsequent runs. No schema migration was required.

**Configurable similarity weights and thresholds (PR #43)**

The hardcoded similarity weights (timing 20%, sequence 35%, protocol 25%, credential 10%, target 10%) and lifecycle thresholds were moved to `app/core/config.py` as environment variables with the previous values as defaults:
- `SIMILARITY_WEIGHT_TIMING`, `SIMILARITY_WEIGHT_SEQUENCE`, `SIMILARITY_WEIGHT_PROTOCOL`, `SIMILARITY_WEIGHT_CREDENTIAL`, `SIMILARITY_WEIGHT_TARGET`
- `CAMPAIGN_DORMANT_DAYS`, `CAMPAIGN_HISTORICAL_DAYS`
- `CLUSTERING_THRESHOLD`

Existing behavior is unchanged when defaults are used.

---

### Group B — AI Integration

**AI backend abstraction (PR #44)**

New module `app/ai/backend.py` provides a uniform `generate(prompt: str) → str` interface:
- `AIBackend` — abstract base class; all backends implement this interface
- `DisabledAIBackend` — raises `AIDisabledError`; default when `AI_BACKEND=none`
- `MockAIBackend` — deterministic fixed-response backend for test injection only
- `OllamaAIBackend` — calls Ollama REST API at `OLLAMA_HOST`; no data leaves the system; `httpx` imported lazily
- `ClaudeAIBackend` — calls Anthropic Claude API; `anthropic` SDK imported lazily; requires `ANTHROPIC_API_KEY`
- `get_ai_backend()` — factory function; reads `AI_BACKEND` setting at call time

New settings: `AI_BACKEND` (none/claude/ollama), `ANTHROPIC_API_KEY`, `AI_MODEL`, `OLLAMA_HOST`, `AI_TIMEOUT_SECONDS`.

**Prompt builder and safety layer (PR #45)**

`app/ai/prompt_builder.py` — pure, side-effect-free prompt construction:
- `build_campaign_summary_prompt(campaign, fingerprint, observations)` — builds a `<data>` XML block with all permitted campaign fields, human-readable behavioral dimension summaries, observation aggregates, and a structured user instruction. Source IPs are never read or included.
- `build_brief_prompt(campaigns)` — builds a `<campaigns>` block with a compact 5-line entry per campaign. Source IPs are never read or included.
- `format_fingerprint_summary(fingerprint)` — converts raw feature JSON into readable per-dimension strings for use in prompts.
- `SYSTEM_PROMPT` and `BRIEF_SYSTEM_PROMPT` — constant system instructions that are never interpolated with user data.

`app/ai/safety.py` — deterministic input and output validation:
- `sanitize_field(value, max_len)` — truncates to `max_len` characters, then scans for 15 injection-pattern regexes. Any match replaces the entire field with `REDACTED_FIELD`.
- `contains_ip_pattern(text)` — detects IPv4 and IPv6 address patterns.
- `redact_ip_patterns(text)` — replaces all IP patterns with `[IP REDACTED]`.
- `validate_ai_output(text, max_len)` — validates AI output in priority order: empty response, IP detected, length exceeded. Returns `(validated_text, rejection_reason)`.
- `within_byte_budget(text, max_bytes)` and `byte_length(text)` — byte-level prompt size utilities.

**Single campaign AI summary endpoint (PR #46)**

`POST /api/campaigns/{campaign_id}/summary` — operator-triggered natural-language summary for a single campaign.

- Auth: `require_jwt_or_api_key`
- Fetches campaign (404 if not found), behavioral fingerprint of the most-recently-active member, and the last 10 observations — all read-only
- Builds structured prompt via `build_campaign_summary_prompt`
- Calls `get_ai_backend().generate()` — all backend errors mapped to HTTP 503
- Validates output via `validate_ai_output(raw_output, max_len=1000)`
- Privacy gate: `PRIVACY_MODE=on` + `AI_BACKEND=claude` → HTTP 422
- Response envelope: `ai_assisted`, `ai_backend`, `generated_at`, `warning`, `campaign_id`, `summary`, `source_records`, `safety_flags`, `rejected`, `rejection_reason`, `truncated`
- No AI output is written to the database

**Dashboard AI summary panel (PR #47)**

`CampaignAiPanel.jsx` — operator-triggered AI summary panel rendered below the existing deterministic `CampaignDetail` expanded row in `Campaigns.jsx`.

- Always-visible warning banner sourced from the server `warning` field, with a hardcoded fallback
- Idle state: "Generate AI Summary" button; the panel never auto-generates
- Loading state: spinner text
- Error state: non-alarming message ("AI summary unavailable") without surfacing raw error details
- Success state: plain text summary rendered as `{data.summary}` in JSX text content — never `dangerouslySetInnerHTML`; truncation indicator; rejection message for safety-rejected outputs; metadata footer with generated_at, backend name, observation count, and safety flags
- Dismiss resets to idle, preserving the Generate button

AI summary state is tracked per campaign in a `aiSummaries` object in `Campaigns.jsx`, keyed by campaign ID. No state is persisted to `localStorage` or any storage mechanism.

**Multi-campaign threat brief endpoint (PR #48)**

`POST /api/campaigns/brief` — operator-triggered threat brief across multiple campaigns.

- Auth: `require_jwt_or_api_key`
- Request body: `BriefRequest` with `max_campaigns: int` (default: 10, ge: 1, le: 25); body is optional — defaults apply when omitted
- Fetches `list_campaigns(limit=max_campaigns*4)`, filters to `{active, dormant, reactivated}` statuses only, caps at `max_campaigns`
- Empty campaign set returns HTTP 200 with `summary: null` and `rejection_reason: "no_campaigns"` — no backend call made
- Builds structured prompt via `build_brief_prompt`
- Calls `get_ai_backend().generate()` — all backend errors mapped to HTTP 503
- Validates output via `validate_ai_output(raw_output, max_len=2500)`
- Privacy gate: same `PRIVACY_MODE` + `AI_BACKEND=claude` → HTTP 422 guard as `/summary`
- Response envelope: `ai_assisted`, `ai_backend`, `generated_at`, `warning`, `summary`, `campaign_count`, `source_records` (with `campaign_ids` list and `campaign_count`), `rejected`, `rejection_reason`, `truncated`
- No AI output is written to the database

---

## What Changed Architecturally

### New modules

```
app/ai/
  __init__.py          Public API re-exporting all AI layer symbols
  backend.py           AIBackend ABC + DisabledAIBackend, MockAIBackend,
                       OllamaAIBackend, ClaudeAIBackend, get_ai_backend()
  prompt_builder.py    build_campaign_summary_prompt(), build_brief_prompt(),
                       format_fingerprint_summary(), SYSTEM_PROMPT,
                       BRIEF_SYSTEM_PROMPT
  safety.py            sanitize_field(), validate_ai_output(),
                       contains_ip_pattern(), redact_ip_patterns(),
                       within_byte_budget(), byte_length()
```

### New router

`app/routers/analyze.py` registered in `app/main.py` under the `/api/campaigns` prefix (shared with `campaigns.py`). All AI endpoints live here to keep the analysis path distinct from the CRUD path in `campaigns.py`.

### New frontend components

`ui/dashboard/src/components/CampaignAiPanel.jsx` — self-contained AI panel component. Stateless; all state lives in `Campaigns.jsx`.

### Ingest path isolation

The AI layer has zero coupling to the ingest path. `app/routers/ingest.py`, `app/intelligence/fingerprint.py`, and `app/intelligence/clustering.py` were not modified in Phase 5. AI calls are only made when an operator explicitly triggers them via an endpoint.

### Backend abstraction boundary

Router code never imports `anthropic` or `httpx` directly. All AI backend logic is encapsulated in `app/ai/backend.py`. Swapping or disabling backends requires only an environment variable change, not a code change.

---

## AI Safety Boundaries Implemented

### Input boundaries

1. **Source IP exclusion** — `build_campaign_summary_prompt` and `build_brief_prompt` never read the `source_ip` key from fingerprint dicts or observation dicts. The exclusion is structural, not filtered: the key is simply not accessed.

2. **Field sanitization** — every string field that originates from campaign records is passed through `sanitize_field()` before inclusion in the prompt. Sanitization applies: character truncation to 200 chars, then scan against 15 injection-pattern regexes. Any match replaces the field with `REDACTED_FIELD`.

3. **Permitted-input allowlist** — prompt builders only read explicitly-named fields from the Section 4 allowlist. Raw event rows, the `audit_log` table, and `source_ips` beyond pre-aggregated counts are never accessed by any AI code path.

4. **Ingest path isolation** — no AI code is on the ingest path. `assign_or_create_campaign()` in `clustering.py` is not modified and does not call any AI function.

### Output boundaries

5. **IP detection in outputs** — `validate_ai_output` checks every AI response for IPv4 and IPv6 patterns before returning it to the caller. Any IP pattern in the output causes `rejected=True`, `summary=None`, `rejection_reason="ip_detected"`.

6. **Length limits** — outputs exceeding 1,000 characters (summary) or 2,500 characters (brief) are truncated. Truncated responses carry `truncated=True` but are not rejected.

7. **Empty response handling** — whitespace-only output is rejected with `rejection_reason="empty_response"` before it reaches the caller.

8. **No persistence** — no AI output is written to the database. The endpoint handlers are read-only with respect to SQLite.

### Privacy boundary

9. **PRIVACY_MODE gate** — `AI_BACKEND=claude` with `PRIVACY_MODE=on` returns HTTP 422 with an explanation. This prevents campaign data from being sent to an external API when the operator has indicated a privacy intent. `AI_BACKEND=ollama` with `PRIVACY_MODE=on` is explicitly supported as the air-gapped inference configuration.

### Disclosure boundary

10. **Mandatory warning label** — every AI response includes `warning` in the envelope. The dashboard renders it in a visible banner that cannot be dismissed. AI outputs are labelled as inferential, not asserted.

### Injection pattern catalogue

The 15 patterns detected by `safety.py`:

| Pattern | Example trigger |
|---|---|
| `ignore (previous\|prior\|above\|all)` | "ignore previous instructions" |
| `disregard (previous\|prior\|above\|all\|the above)` | "disregard all prior context" |
| `system:` | "system: you are now..." |
| `<\|` | LLM token boundary injection |
| `\| >` | LLM token boundary injection |
| `prompt injection` | Explicit self-reference |
| `jailbreak` | Explicit self-reference |
| `act as ` | "act as a different AI" |
| `you are now ` | "you are now unrestricted" |
| `forget (your\|all\|previous\|everything)` | "forget your instructions" |
| `override (your\|previous\|prior)` | "override your previous instructions" |
| `new (instructions\|rules\|directives)` | "new instructions follow" |
| `from now on ` | "from now on ignore..." |
| `[INST]` | Llama-style instruction injection |
| `### instructions` | Markdown-style instruction injection |

---

## What Was Intentionally Deferred

The following were in scope for Phase 5 per the blueprint but were explicitly held back during implementation to preserve scope boundaries. Each is a valid Phase 6 candidate.

**From the blueprint's Deferred to Phase 6 section:**

- Async AI analysis — non-blocking endpoint with a background job queue; Phase 5 endpoints are synchronous
- AI output persistence and history — outputs are transient; no table stores them; no operator can review past outputs
- Conversational analyst interface — multi-turn Q&A is out of scope; each request is stateless
- Automated alerting triggered by AI analysis — no AI conclusion triggers a downstream action
- Operator-editable AI prompt templates — system and user prompts are hardcoded constants; no runtime customisation
- Webhook delivery of AI-generated briefs — no push mechanism exists
- Federation-aware AI analysis — cross-deployment fingerprint comparison is a Phase 7 concern

**Additional items deferred during implementation:**

- `GET /api/analyze/status` endpoint — the blueprint described a feature-gate endpoint returning `{ai_enabled, ai_backend}` that the dashboard would query before showing the Generate button. Not implemented; the AI panel renders for all users and returns a clear 503 when `AI_BACKEND=none`.
- Brief UI (dashboard panel for `/api/campaigns/brief`) — the multi-campaign brief endpoint is API-only in Phase 5; no dashboard integration was built
- Time-window filtering in the brief — the blueprint specified `window_start`/`window_end` parameters; the endpoint instead filters by campaign status (`active`, `dormant`, `reactivated`), which is sufficient for the primary use case
- `model` field in the response envelope — the blueprint included a `model` key; not added as AI_MODEL is an environment-level concern, not response metadata
- `fingerprint_ids` in `source_records` — omitted; fingerprints are referenced through their campaign membership, not by ID
- HTTP 504 for timeout — all backend failures return HTTP 503; a separate 504 code was considered but adds complexity without operator-visible benefit at this stage
- Retry on AI backend timeout — the backend makes a single attempt; a retry would require changing the synchronous flow or adding async infrastructure
- Audit logging of AI payload byte counts — the blueprint (§5) specified logging each external AI call to `audit_log` with timestamp and byte count; not implemented; deferred with the rate-limiting work
- AI request rate limiting (`AI_MAX_REQUESTS_PER_MINUTE`) — no per-deployment rate limit is enforced on the AI endpoints; deferred to Phase 6 when async infrastructure makes it tractable

---

## Known Limitations

**Synchronous latency.** AI endpoints are synchronous. A slow or busy Claude/Ollama backend holds the HTTP connection open until the response arrives. This is acceptable at low operator concurrency but will degrade under load. The fix is async processing with a job queue (Phase 6).

**No brief UI.** `POST /api/campaigns/brief` is callable via API but has no dashboard panel. Operators who want a threat brief must call the endpoint directly or use a tool that can issue POST requests.

**No AI feature gate in the dashboard.** The `CampaignAiPanel` renders for all operators regardless of `AI_BACKEND` setting. When `AI_BACKEND=none`, clicking "Generate AI Summary" returns a 503 with a clear error message. This is functional but not ideal — the panel could be hidden or the button disabled when AI is not configured.

**No AI output history.** There is no way to recall a previously generated summary. Each Generate click is a fresh API call. Operators who want to record a summary must copy-paste it manually.

**Injection defence is best-effort.** The 15-pattern injection scan in `safety.py` covers known attack patterns against instruction-following models. It is not exhaustive. A sufficiently creative adversarial campaign name or observation note could potentially contain an injection that evades pattern matching. The structural defence (field-level truncation, explicit key allowlist) is more reliable than the pattern scan.

**IPv6 detection in outputs is pattern-based.** The IPv6 regex in `safety.py` is conservative enough to catch common formats but may miss highly compressed or unusual forms. IPv4 detection is comprehensive.

**Brief status filter is not time-windowed.** The brief endpoint returns campaigns filtered by lifecycle status, not by a time window. A dormant campaign that has been inactive for 11 months would be included. Operators who want a time-bounded brief must post-filter the results themselves.

---

## Operational Risks

**AI_BACKEND=claude with a compromised campaign name.** If an adversary controls a honeypot that injects a crafted campaign name into the database, and that name reaches the prompt builder, `sanitize_field` applies truncation and injection-pattern scanning. A campaign name that passes the safety scan and contains instructions would be forwarded to the Claude API. Mitigation: the 200-character truncation and 15 injection patterns provide reasonable defence; the Anthropic API also applies its own content safety layer.

**ANTHROPIC_API_KEY exposure.** The API key is stored as an environment variable. Exposure of the `.env` file or process environment leaks the key. Mitigation: same as any secret in this deployment model; `.env` is in `.gitignore`; the key is not logged or included in any API response.

**Ollama without authentication.** `OllamaAIBackend` calls the Ollama REST API with no authentication. If `OLLAMA_HOST` points to a network-accessible Ollama instance, any host that can reach it can submit requests. Mitigation: bind Ollama to localhost; use a network firewall to restrict access.

**Synchronous endpoint abuse.** A caller with a valid API key can repeatedly call `/api/campaigns/{id}/summary` or `/api/campaigns/brief`, causing repeated external API calls at the operator's expense. There is no per-endpoint rate limit. Mitigation: defer to Phase 6 rate limiting; restrict API key distribution.

**No audit trail for AI calls.** The blueprint (§5) specified that external AI API calls should be logged to `audit_log` with timestamp and payload byte count. This was not implemented. An operator cannot currently determine when or how frequently the Claude API was called from audit records alone. Mitigation: implement AI call audit logging in Phase 6.

---

## Testing and Validation Summary

### Test counts

| Test file | Type | Tests |
|---|---|---|
| `tests/unit/test_ai_backend.py` | Unit | 25 |
| `tests/unit/test_ai_prompt_builder.py` | Unit | 50 |
| `tests/unit/test_ai_safety.py` | Unit | 66 |
| `tests/integration/test_analyze_endpoints.py` | Integration | 106 |
| **AI layer total** | | **247** |
| **Full suite** | | **948 passed, 3 skipped** |

### What the tests verify

**`test_ai_safety.py` (66 tests)**
- All 15 injection patterns are detected
- Injection detection is case-insensitive
- Truncation is applied before injection scanning
- `REDACTED_FIELD` is returned on injection detection
- Clean fields pass through unmodified
- `validate_ai_output` rejects empty/whitespace-only responses
- `validate_ai_output` rejects outputs containing IPv4 and IPv6 patterns
- Outputs at exactly `max_len` are not truncated; outputs at `max_len + 1` are
- `contains_ip_pattern` and `redact_ip_patterns` cover IPv4 and IPv6 forms
- `within_byte_budget` and `byte_length` are correct for multi-byte UTF-8

**`test_ai_prompt_builder.py` (50 tests)**
- `build_campaign_summary_prompt` includes all expected campaign fields
- Fingerprint dimension summaries are included when fingerprint is present
- `no_fingerprint` safety flag is set when fingerprint is absent
- `low_confidence` safety flag is set when confidence < 0.50
- Source IPs from fingerprint fixtures and observation fixtures do not appear in the built prompt
- Observation count, reactivation event count, and clustering notes appear correctly
- Field sanitization is applied to campaign name and clustering notes
- `build_brief_prompt` includes all campaigns in the `<campaigns>` block
- Empty campaign list produces a well-formed prompt without crashing
- `source_records` contains `campaign_ids` and `campaign_count`

**`test_ai_backend.py` (25 tests)**
- `get_ai_backend()` returns `DisabledAIBackend` for `AI_BACKEND=none`
- `DisabledAIBackend.generate()` raises `AIDisabledError`
- `MockAIBackend` returns its configured response without network calls
- `ClaudeAIBackend` maps `anthropic.APITimeoutError` → `AIBackendError`
- `ClaudeAIBackend` maps `anthropic.APIConnectionError` → `AIBackendUnavailableError`
- `ClaudeAIBackend` maps `anthropic.AuthenticationError` → `AIBackendError`
- `OllamaAIBackend` maps `httpx.ConnectError` → `AIBackendUnavailableError`
- `OllamaAIBackend` maps `httpx.TimeoutException` → `AIBackendError`
- Missing `anthropic` package raises `AIBackendError` with install instruction
- Missing `httpx` package raises `AIBackendError` with install instruction
- `get_ai_backend()` raises `AIBackendError` for unrecognised backend name

**`test_analyze_endpoints.py` (106 tests)**
- `POST /api/campaigns/{id}/summary` returns 404 on missing campaign
- `POST /api/campaigns/{id}/summary` returns 503 when `AI_BACKEND=none`
- `POST /api/campaigns/{id}/summary` returns 422 when `PRIVACY_MODE=on` + `AI_BACKEND=claude`
- `ai_assisted: true` is present on every 200 response
- `warning` field is present and non-empty on every 200 response
- `source_records` with `campaign_id`, `fingerprint_present`, `observation_count` on every 200
- Output containing an IPv4 pattern produces `rejected=true`, `summary=null`
- Output exceeding 1,000 characters is truncated and `truncated=true`
- No database write occurs after a summary call (verified via `updated_at` comparison)
- `POST /api/campaigns/brief` returns 503 when `AI_BACKEND=none`
- `POST /api/campaigns/brief` returns 422 when `PRIVACY_MODE=on` + `AI_BACKEND=claude`
- Default `max_campaigns=10` is applied when no body is sent
- `max_campaigns=26` returns 422; `max_campaigns=0` returns 422; `max_campaigns=25` returns 200
- Historical campaigns are excluded from the brief
- Dormant and reactivated campaigns are included in the brief
- Empty campaign set returns 200 with `campaign_count=0`, `rejection_reason="no_campaigns"`
- `source_records.campaign_ids` contains all included campaign IDs
- Output containing an IP pattern produces `rejected=true`, `summary=null`
- Output exceeding 2,500 characters is truncated and `truncated=true`
- No database write occurs after a brief call

### No live AI calls in tests

No test makes a call to the Claude API or a real Ollama endpoint. All integration tests inject `MockAIBackend` via `monkeypatch.setattr("app.routers.analyze.get_ai_backend", lambda: MockAIBackend(...))`. The `ANTHROPIC_API_KEY` is not required for the test suite to pass.

---

## Recommended Phase 6 Direction

Phase 5 proved the core AI concept: structured campaign data can be translated into operator-useful natural language, with deterministic safety boundaries enforced at both the input and output layers.

Phase 6 has two logical directions and should pursue both in sequence:

### Direction 1 — AI infrastructure maturity

The three most pressing Phase 5 limitations all share a root cause: synchronous, stateless, ephemeral AI calls.

**Async AI with a background job queue.** Replace the synchronous endpoint pattern with a two-step model: the POST endpoint enqueues a job and returns a job ID; the operator polls `GET /api/campaigns/{id}/summary/{job_id}` for the result. This decouples operator latency from AI backend latency and makes rate limiting natural. FastAPI `BackgroundTasks` is sufficient for Phase 6; Celery or asyncio workers are Phase 7 considerations.

**AI output persistence.** Store completed AI outputs in a new `ai_outputs` table with `campaign_id`, `output_type`, `content`, `generated_at`, `ai_backend`, `model`, `rejected`, `rejection_reason`, `truncated`. This enables operators to recall past outputs, supports audit requirements, and provides training signal for future model improvements.

**AI call audit logging.** Implement the §5 blueprint requirement: log every external AI API call to `audit_log` with timestamp, endpoint called, and byte count of the payload. This closes the audit gap noted in Operational Risks above.

**Rate limiting.** Add per-API-key rate limiting to the AI endpoints. Implement `AI_MAX_REQUESTS_PER_MINUTE` as specified in the blueprint. Prevents accidental or intentional API cost exhaustion.

### Direction 2 — Campaign brief dashboard integration

The multi-campaign brief endpoint is complete but has no dashboard surface. A brief panel in the dashboard would be the most immediately useful UI addition for Phase 6:
- A "Generate Threat Brief" button in the campaign panel header (not per-campaign)
- Brief rendered below the campaign list with the same warning banner pattern as `CampaignAiPanel`
- Show `campaign_count` and `source_records.campaign_ids` as attribution metadata
- Dismiss pattern identical to single-campaign summary

This is a contained, well-scoped UI task that mirrors the pattern already established in PR #47.

### What Phase 6 should not add

- Conversational interfaces — require session management and persistent conversation history; premature before output persistence is implemented
- AI involvement in clustering — `clustering.py` must remain deterministic and AI-independent
- Automated alerting triggered by AI conclusions — AI outputs require operator review before any automated downstream action
- Fine-tuning or model training — Phase 6 uses foundation models only

---

*Cross-references: [PHASE_5_BLUEPRINT.md](PHASE_5_BLUEPRINT.md) · [PHASE_4_CLOSEOUT.md](PHASE_4_CLOSEOUT.md) · [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md)*
