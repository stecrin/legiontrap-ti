# LegionTrap TI — Phase 6 Architecture Blueprint

**Document type:** Pre-implementation architecture blueprint
**Status:** Under review — do not begin implementation until this document is approved
**Audience:** Engineers, contributors
**Date:** 2026-05-27

---

## §1 Phase 6 Mission

Phase 5 proved the AI concept: structured campaign data can be translated into useful natural language under controlled safety conditions, with deterministic evidence always visible alongside AI interpretation. That proof is sufficient. Phase 5 does not leave a capability gap; it leaves an infrastructure gap that must be closed before the AI layer can be trusted at operational scale.

Phase 6 has two complementary missions that must be developed in parallel:

**Mission 1: Make AI-generated intelligence a first-class, accountable, recall-able, auditable artifact of the platform.** Phase 5 AI is honest but unaccountable. You cannot prove it ran. You cannot recall what it said about a campaign last month. You cannot determine whether the same campaign summary produced different conclusions on different days. You cannot account for how many times campaign data was sent to an external API or at what cost. These are not UX limitations — they are architectural gaps that become compliance, trust, and forensic liabilities the moment the system is used in a consequential operational context.

**Mission 2: Deepen the behavioral memory layer from a snapshot model into a longitudinal model.** The current fingerprint describes an actor at a point in time. There is no mechanism to say "this campaign's timing pattern has shifted from 2-second intervals to 5-second intervals over the past 6 months." That drift is potentially the most intelligence-rich signal the system can produce — evidence of deliberate behavioral adaptation, which is qualitatively different from static behavior. Phase 6 must begin collecting the longitudinal data that Phase 7 will use for metamorphic detection.

Phase 6 is the transition from a query tool to an intelligence asset with memory. It is not "more AI features." Features come after the foundation is correct.

---

## §2 Architectural Philosophy

### The governing principle for Phase 6

**Infrastructure must precede features.** Every Phase 6 AI feature depends on the infrastructure in Group A. Adding AI features without first closing the async, persistence, and audit gaps produces a system that grows its surface area without growing its trustworthiness. The PR sequence enforces this: Group A ships as a complete block before Group C begins.

### Continuity with Phase 4 and Phase 5

Phase 4 established the deterministic clustering and behavioral fingerprint model. Phase 5 added the AI interpretation layer with explicit safety boundaries. Phase 6 must preserve every architectural invariant established in those phases while extending the system in depth, not in breadth. The clustering algorithm remains deterministic and unmodified. The AI layer remains additive and read-only. The ingest path remains fully isolated from all AI operations.

### Accountability as a first-class concern

Phase 5 demonstrated that AI can produce useful output. Phase 6 must demonstrate that the system can account for that output: who requested it, when, from what data state, by which model, with what safety outcomes, at what cost. Accountability is not a compliance formality — it is the mechanism by which operator trust is earned and maintained over time.

### Behavioral continuity over point-in-time snapshots

The long-term intelligence value of the platform is proportional to the depth of its behavioral memory. Behavioral memory that answers "what is this campaign doing now?" is useful. Behavioral memory that answers "how has this campaign's behavior changed over the past 18 months?" is irreplaceable. Phase 6 begins the transition to the second kind.

---

## §3 Deterministic-First Invariants

These invariants are established by Phases 4 and 5 and are permanently non-negotiable. They may not be relaxed in any Phase 6 PR under any circumstance.

| Invariant | Statement |
|---|---|
| Clustering is deterministic | `app/intelligence/clustering.py` makes campaign membership decisions using the weighted similarity algorithm. AI has no role in these decisions. |
| AI is read-only | No AI code path writes to any table except the AI output tables introduced in Phase 6. The campaign, fingerprint, event, and observation tables are never written by AI operations. |
| Ingest path isolation | `app/routers/ingest.py` and `app/intelligence/` have zero imports from `app/ai/`. AI latency cannot block event ingestion under any configuration. |
| No AI-triggered state transitions | Campaign lifecycle transitions (active → dormant → historical → reactivated) are deterministic and time-based. AI may describe a campaign's trajectory; it may never cause a transition. |
| AI outputs are never AI inputs | No AI prompt is constructed using a previously generated AI output as context. Briefs consume raw campaign data from the database. Summaries consume fingerprint and observation data from the database. The chain from AI output back to the database is never traversed in prompt construction. |
| Warning label is mandatory and non-dismissible | Every AI response includes a `warning` field. The dashboard renders it as a prominent, permanent banner. It is never collapsed, tooltipped, or made optional. |
| Source records are always present | Every AI response includes `source_records` citing the specific data used. The dashboard renders these alongside the AI output so operators always see the evidential basis. |
| No AI involvement in export generation | STIX bundles, pf.conf outputs, UFW lists, ATT&CK Navigator layers, and all IOC exports are derived entirely from deterministic data. AI may not suggest, augment, or modify export content. |

---

## §4 What AI Is Permitted to Do in Phase 6

Phase 6 extends the Phase 5 permitted operations. All Phase 5 permissions continue.

| Operation | Input | Output | New in Phase 6 |
|---|---|---|---|
| Summarize a single campaign | Campaign record + fingerprint features + recent observations | Natural-language paragraph | No — Phase 5 |
| Generate a multi-campaign threat brief | Set of campaign records | Structured narrative brief | No — Phase 5 |
| Generate a time-windowed brief | Campaigns filtered by last_seen time window | Structured narrative brief | Yes — Phase 6 |
| All operations above, persisted | Same as above | Same, written to `ai_outputs` | Yes — Phase 6 |
| All operations above, executed asynchronously | Same as above | Job ID + polling endpoint | Yes — Phase 6 |

All operations remain read-only. All operations produce output for human operators, never for automated downstream systems.

---

## §5 What AI Must Never Do

These prohibitions are absolute. They extend and reinforce the Phase 5 prohibitions.

| Prohibition | Reason |
|---|---|
| Contribute to campaign membership decisions | AI-assigned membership is neither deterministic nor auditable |
| Write to campaigns, fingerprints, events, or observations | The AI layer is a read-only consumer of these tables |
| Consume another AI output as prompt input | Prevents recursive hallucination amplification |
| Trigger campaign lifecycle transitions | Lifecycle transitions are deterministic and time-based |
| Appear in the ingest path | LLM latency must never block event ingestion |
| Trigger alerts or notifications autonomously | AI conclusions require operator review before any downstream action |
| Generate or modify IOC exports | Exports must remain deterministic and independently verifiable |
| Make attribution claims with asserted certainty | Attribution must always be framed as inference, not fact |
| Consume raw event records directly | AI context is limited to pre-aggregated fingerprints and campaign summaries |
| Override a deterministic similarity score | Similarity is computed by `app/intelligence/similarity.py`; AI may describe it, not replace it |
| Execute outside of an explicit operator-triggered request | No scheduled AI generation, no trigger-based generation, no background AI analysis |
| Generate content for adversaries | All AI outputs are for operators; adversary-facing response generation belongs in a separate deception module (Phase 8+) |

---

## §6 Infrastructure-First Doctrine

Phase 6 has five infrastructure prerequisites. All five must be complete before any Group C AI feature expansion begins.

**Prerequisite 1: Async job execution framework with persistent job table.** Phase 5 AI calls are synchronous. Under operator concurrency, this produces connection timeouts, duplicate calls, and wasted API spend. The `processing_jobs` table and the 202 Accepted API contract must exist before the brief dashboard panel is built, before output history is added, and before any rate-limiting logic is implemented. Every subsequent Phase 6 AI feature is built on this contract.

**Prerequisite 2: AI output persistence.** Every AI-generated artifact must be written to `ai_outputs` before being returned to the caller. Without persistence, there is no output history, no recall capability, no audit trail, and no stable `ai_output_id` to reference in future features. The table must be designed once, correctly, as write-once with full provenance metadata.

**Prerequisite 3: AI call audit logging.** Every external AI API call must be logged with timestamp, job_id, backend, model, payload byte count, response byte count, and latency. Never content — only metadata. This closes the compliance gap: an operator must be able to answer "what data left this system this month" from audit records alone. This is not optional for any deployment that handles data subject to regulatory oversight.

**Prerequisite 4: Per-key rate limiting on AI endpoints.** Without rate controls, every AI feature is an unbounded cost surface. Rate limiting must be implemented before the brief dashboard panel is added, because the panel makes it trivial to trigger repeated brief calls.

**Prerequisite 5: `job_id` in all AI response envelopes.** The current response envelope has no `job_id` field. Adding `job_id` after dashboard code is built against the current envelope is a breaking change. It must be introduced simultaneously with the async framework.

These five are the Group A PRs. They ship as a complete block. No Group C work begins until all five are in production.

---

## §7 Async AI Execution Architecture

### §7.1 Design principle

The API contract must be designed for the mature async model from the first Phase 6 PR, even if the initial implementation uses FastAPI BackgroundTasks. Later replacing BackgroundTasks with Celery workers or asyncio workers must be an implementation detail, not an API or schema change.

### §7.2 Processing jobs table

The `processing_jobs` table is the central coordination artifact for all async operations. It serves three purposes simultaneously: async AI execution tracking, clustering deduplication (replacing the in-memory `_pending_ips` set), and rate limiting state.

Required columns and their rationale:

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID, PK | Stable job identity; returned to callers immediately |
| `job_type` | string | `campaign_summary`, `campaign_brief`, `fingerprint_clustering` |
| `status` | enum | `pending`, `running`, `complete`, `failed`, `timed_out` |
| `campaign_id` | UUID, nullable FK | For summary jobs; null for brief jobs |
| `request_json` | JSON | The full request parameters; enables job replay and audit |
| `created_at` | timestamp | When the job was enqueued |
| `started_at` | timestamp, nullable | When the job executor began work |
| `completed_at` | timestamp, nullable | When the job finished (any terminal state) |
| `error_message` | text, nullable | Error detail for failed/timed_out jobs |
| `ai_output_id` | UUID, nullable FK | Set on completion; links to the persisted result |
| `operator_identity` | string | API key hash or JWT subject; who triggered this job |
| `request_byte_count` | integer | Byte count of the assembled prompt; for audit |

The `status` enum must have explicit `failed` and `timed_out` states. Silent failure is not acceptable. A job stuck in `running` for longer than `AI_TIMEOUT_SECONDS × 2` must be transitioned to `timed_out` by a cleanup process. Without this, dashboard polling code enters infinite loops and the jobs table accumulates ghost records.

### §7.3 API contract

The async API contract is a permanent commitment. Once callers depend on `job_id` in responses, the contract cannot change.

**POST /api/campaigns/{id}/summary**
- Returns: HTTP 202 Accepted
- Body: `{ "job_id": "<uuid>", "status": "pending", "poll_url": "/api/jobs/<uuid>" }`
- Behavior: enqueues a job, returns immediately

**POST /api/campaigns/brief**
- Returns: HTTP 202 Accepted
- Body: same shape as summary

**GET /api/jobs/{job_id}**
- Returns: HTTP 200 with job record
- Body includes: `status`, `ai_output_id` (when complete), `error_message` (when failed), `created_at`, `completed_at`
- Terminal states: `complete`, `failed`, `timed_out` — polling stops when any of these is reached

**GET /api/jobs/{job_id}/result**
- Returns: HTTP 200 with the full AI output envelope when `status=complete`
- Returns: HTTP 409 with `{"status": "<non-complete-status>"}` when job is not yet complete
- Returns: HTTP 404 when job_id is unknown

### §7.4 Failure modes

| Failure condition | Response |
|---|---|
| AI backend unreachable | Job transitions to `failed`; `error_message` set; GET /jobs/{id} shows `status: failed` |
| AI backend timeout | Job transitions to `timed_out` after `AI_TIMEOUT_SECONDS × 2` |
| Output rejected (IP detected) | Job completes; `ai_outputs` record has `rejected=true`; operator sees rejection reason |
| Output truncated | Job completes; `ai_outputs` record has `truncated=true`; truncated text returned |
| `AI_BACKEND=none` | Job transitions to `failed` immediately with `AI features are disabled` error message |
| `PRIVACY_MODE=on` + `AI_BACKEND=claude` | HTTP 422 returned at POST time; no job created |
| Campaign not found | HTTP 404 returned at POST time; no job created |

### §7.5 Background tasks to worker queue: the evolution path

**Phase 6 implementation:** FastAPI BackgroundTasks writing to `processing_jobs`. Adequate for single-deployment, low-to-moderate concurrency. Simple to implement, simple to debug.

**Phase 6/7 upgrade path:** When BackgroundTasks proves insufficient — measured by job queue depth growing faster than it's drained, or by missed TTL deadlines accumulating — replace the BackgroundTasks executor with Celery workers + Redis broker, or an asyncio worker pool. The API contract (`job_id`, status polling, result endpoint), the `processing_jobs` table schema, and the dashboard polling logic are unchanged. The upgrade is an implementation swap, not an architectural change.

The decision to upgrade must be measurement-driven. Do not add a task queue for theoretical future concurrency that has not been observed.

---

## §8 AI Output Persistence Architecture

### §8.1 Design principles

The `ai_outputs` table is a permanent institutional record. Its design must anticipate years of use and regulatory scrutiny. Two principles govern its design:

**Write-once semantics.** An AI output is an immutable historical fact: at time T, given data state S, model M produced output O. Modifying O erases the historical fact. Corrections produce new records. An operator who wants to refresh a summary triggers a new job; the old output persists with its original `generated_at` timestamp. The history is append-only. Deletion of individual records requires explicit administrative action with a logged justification.

**Full provenance, not just content.** The content of an AI output is only useful if its evidential basis is recorded alongside it. Every record must carry enough metadata to reconstruct: what data was used, who triggered the generation, which model produced it, and whether the output passed safety validation.

### §8.2 Required columns and their rationale

| Column | Type | Rationale |
|---|---|---|
| `id` | UUID, PK | Stable output identity; referenced by jobs, UI, audit |
| `job_id` | UUID, FK to processing_jobs | Links output to the job that produced it |
| `output_type` | string | `campaign_summary`, `campaign_brief`; enables type-specific queries |
| `campaign_id` | UUID, nullable FK | Set for summaries; null for briefs |
| `campaign_ids_json` | JSON array, nullable | Set for briefs; lists all campaign IDs included |
| `content` | text, nullable | The AI-generated text; null when rejected |
| `ai_backend` | string | `claude`, `ollama`, `none` |
| `model_name` | string, indexed | The specific model identifier; critical as models evolve |
| `prompt_hash` | string | SHA-256 of the user_prompt; not the prompt itself |
| `prompt_byte_count` | integer | Payload size for audit; no content stored |
| `safety_flags_json` | JSON array | The flags from prompt_builder (e.g., `low_confidence`) |
| `rejected` | boolean | True when output failed safety validation |
| `rejection_reason` | string, nullable | `ip_detected`, `empty_response`, or null |
| `truncated` | boolean | True when output was cut to the length limit |
| `source_records_json` | JSON | The source_records dict: campaign_id(s), fingerprint_present, observation_count |
| `data_quality_score` | float, nullable | Derived from observation count, fingerprint completeness, confidence score |
| `generated_at` | timestamp | When the AI call completed; not when the job was created |
| `operator_identity` | string | API key hash or JWT subject; who triggered this output |

### §8.3 Model name as a first-class column, not a JSON field

Model names change with every new release. "What conclusions did the system produce with claude-haiku vs. claude-sonnet?" is a legitimate operational question. "Did the model upgrade change how campaigns of a specific type are described?" requires grouping by model. This column must be indexed and queryable, not buried in a JSON blob.

### §8.4 Prompt hash, not prompt content

The full user prompt for a campaign summary can be several kilobytes. Storing the prompt in every row adds significant table size without commensurate audit value. The SHA-256 of the user prompt serves the audit purpose: were two outputs generated from equivalent data states? If two records have the same `prompt_hash`, they were generated from the same prompt text. If they differ, the underlying data changed between generations. The full prompt can be reconstructed from `source_records_json` + the prompt builder code at the hash timestamp if investigation requires it.

### §8.5 Data quality score

The `data_quality_score` is a composite metric derived from deterministic data: campaign confidence score, observation count, fingerprint dimension completeness (fraction of 5 dimensions non-null), and recency of last observation. It is computed at job execution time and stored alongside the AI output. It enables the UI to surface a data quality indicator alongside the AI summary — "Generated from 3 observations, sparse fingerprint, confidence 0.55" — without requiring the operator to navigate to the campaign detail to make that assessment.

A campaign with 2 observations and a sparse fingerprint whose AI summary is presented without data quality context trains operators to trust AI summaries uncritically. The data quality score makes the evidential basis visible at the same level of prominence as the content.

### §8.6 Provenance chain navigation

The provenance chain runs: `ai_outputs` → `source_records_json` → `campaigns` → `campaign_observations` → `behavioral_fingerprints` → `campaign_members` → (masked) source IPs. Phase 6 should add a provenance traversal endpoint: `GET /api/ai-outputs/{id}/provenance` returning the full chain with current data state alongside the generation-time snapshot. This transforms provenance from a stored JSON blob into an investigable chain.

---

## §9 AI Audit Logging Architecture

### §9.1 What to log

Every call to an external AI backend must produce an audit record. Audit records contain metadata about the call, never the content.

Required audit fields per AI call:

| Field | Notes |
|---|---|
| `timestamp` | UTC; when the call was made |
| `job_id` | Links to the processing_jobs record |
| `ai_output_id` | Links to the result (null if job failed before output was written) |
| `backend` | `claude`, `ollama` |
| `model_name` | The specific model called |
| `payload_bytes` | Byte count of the user prompt sent |
| `response_bytes` | Byte count of the raw response received; 0 on failure |
| `latency_ms` | Wall-clock time of the backend call |
| `status` | `success`, `failure`, `timeout` |
| `error_type` | `AIBackendUnavailableError`, `AIBackendError`, `AIDisabledError`, or null |
| `operator_identity` | API key hash or JWT subject |

**Content is never logged.** The prompt content and response content are not stored in audit records. The operator's data and the AI's interpretation of it exist only in `ai_outputs`. The audit log records that a call happened, not what was said.

### §9.2 Storage location

Extend the existing `audit_log` table with a `log_type` discriminator column, or create a dedicated `ai_audit_log` table. The dedicated table is preferred: it allows independent retention policies (AI audit records may need to be retained longer than ingest audit records for compliance purposes) and avoids inflating the ingest audit log with AI call records.

### §9.3 Rate limiting

`AI_MAX_REQUESTS_PER_MINUTE` is added as a setting (default: 10) and enforced per API key. Rate limit state is tracked in the `processing_jobs` table (count of jobs created by this API key in the last 60 seconds). When the limit is exceeded:
- The POST endpoint returns HTTP 429 Too Many Requests
- The response includes `Retry-After` header
- No job is created
- The rate limit event is logged to `ai_audit_log` with `status: rate_limited`

The default of 10 requests per minute is conservative. Operators who need higher limits can configure `AI_MAX_REQUESTS_PER_MINUTE` explicitly, making the decision visible and intentional rather than unlimited.

### §9.4 Admin audit API

`GET /api/admin/ai-audit` (API key only, not JWT) returns AI audit records with optional filters: time range, backend, status, operator_identity. This is the endpoint an operator queries to answer "what data left this system in the last 30 days?" for compliance or cost review purposes.

---

## §10 Operator Trust Preservation Rules

These rules exist to prevent AI theater: the state where AI-generated outputs look authoritative, operators treat them as ground truth, and the deterministic evidence that grounded them becomes invisible. Each rule is binding on all Phase 6 implementation decisions.

**Rule 1: AI outputs are never inputs to other AI operations.**
The brief prompt consumes raw campaign data from the database. It never consumes stored AI summaries. A summary prompt consumes fingerprint and observation data. It never consumes a previously generated summary. The chain from AI output back to the database is never traversed in prompt construction. This is the most important single rule for preventing compounded hallucination.

**Rule 2: Persistence must never imply currency.**
When a stored AI output is displayed, its `generated_at` timestamp must be as visually prominent as its content. An AI summary from 3 months ago is historical intelligence, not current intelligence. The UI must make this distinction explicit. The system must never present a stored output in a way that implies it reflects the campaign's current state.

**Rule 3: The deterministic data panel remains primary.**
In every context where an AI output is shown, the campaign's current deterministic state (confidence score, observation count, member IP count, similarity dimension breakdown, last seen, lifecycle status) must be visible at the same level of prominence. When an AI output history panel is displayed, the campaign's current deterministic state is shown alongside the historical output for comparison — not hidden behind a click.

**Rule 4: Uncertain associations must be surfaced, not hidden.**
The `DECISION_UNCERTAIN_ASSOCIATION` label in `campaign_observations.notes` is currently stored but not prominently surfaced. An operator who sees a campaign with 12 observations cannot currently tell how many were automatic associations vs. uncertain ones. This is a material omission: a campaign built on uncertain associations should be treated differently from one built on certain associations. Phase 6 must surface this distinction explicitly in the campaign detail view and the AI summary request flow.

**Rule 5: No AI-triggered state transitions, ever.**
Campaign lifecycle transitions are deterministic and time-based, driven by `CAMPAIGN_DORMANT_DAYS` and `CAMPAIGN_HISTORICAL_DAYS`. AI outputs may describe a campaign's trajectory and characterize its behavioral state. They may never trigger, suggest for operator approval, or influence a lifecycle transition. This invariant is enforced at the code level: the lifecycle maintenance job has no dependency on `app/ai`.

---

## §11 Behavioral Memory Evolution

### §11.1 The snapshot problem

The current behavioral fingerprint is a snapshot: a description of how an actor behaved up to a given observation window. When a campaign reactivates and new fingerprint features are computed, the new values replace the old ones in `behavioral_fingerprints`. There is no record of the behavioral trajectory. The system can answer "what is this campaign doing now?" but cannot answer "how has this campaign's behavior changed over 18 months?"

Behavioral trajectory is the most intelligence-rich signal the system can produce for long-running campaigns. An actor whose timing interval has drifted from 1.5 seconds to 2.0 seconds to 2.5 seconds over 8 months is showing deliberate behavioral adaptation — a metamorphic shift. An actor whose timing interval has been consistent at 2.0 seconds ± 0.1 seconds over the same period is operationally stable. These two cases call for different analytical treatment and different operator responses. The current data model cannot express the difference.

### §11.2 Fingerprint history table

A `fingerprint_history` table preserves each computed fingerprint as a time-series record. The `behavioral_fingerprints` table retains the current fingerprint for clustering (its purpose is unchanged). The history table accumulates the trajectory.

Required columns:

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID, PK | Record identity |
| `source_ip` | string | The IP whose fingerprint was computed |
| `campaign_id` | UUID, nullable FK | The campaign this IP was associated with at computation time |
| `fingerprint_version` | integer | The schema version of the computed features |
| `timing_features` | JSON | Full feature dict at this observation |
| `sequence_features` | JSON | Full feature dict at this observation |
| `protocol_features` | JSON | Full feature dict at this observation |
| `credential_features` | JSON | Full feature dict at this observation |
| `target_features` | JSON | Full feature dict at this observation |
| `confidence` | float | The fingerprint confidence score at computation time |
| `observation_count` | integer | Number of events used to compute this fingerprint |
| `computed_at` | timestamp | When this fingerprint was computed |
| `trigger_type` | string | `initial_computation`, `reactivation`, `periodic_refresh` |

The `fingerprint_history` table is append-only. Records are never modified. Each fingerprint computation appends a new row. The history accumulates over the lifetime of the campaign.

### §11.3 Behavioral stability scoring

The behavioral stability score measures how much a specific dimension has drifted across observations. It is computed from the `fingerprint_history` records for a campaign.

Per-dimension stability is the inverse of the variance in that dimension's feature values across all history records. A timing dimension with consistent 2.0s ± 0.1s intervals has high stability. A timing dimension that ranges from 1.2s to 4.7s has low stability.

The composite behavioral stability score is the weighted average of per-dimension stability scores, using the same dimension weights as the similarity function (timing 20%, sequence 35%, protocol 25%, credential 10%, target 10%).

Stability scores serve two purposes:
1. A data quality signal for AI summaries: "this campaign has been behaviorally stable for 6 months" vs. "this campaign shows high behavioral variance across observations."
2. A metamorphic detection signal: a large drop in stability score between consecutive fingerprint computations may indicate the actor has changed their tooling or operational approach.

The stability score is stored in a `behavioral_stability_score` column on the `campaigns` table (updated by the fingerprint computation job) and included in the campaign detail API response and prompt builder context.

### §11.4 Fingerprint versioning contract

The `fingerprint_version` column exists in `behavioral_fingerprints`. The contract for comparing cross-version fingerprints does not currently exist. This must be defined before any new fingerprint features are added, because clustering attempts to compare fingerprints from different computation times, and if those fingerprints were computed by different versions of the extraction code, the comparison may be semantically invalid.

The Phase 6 fingerprint versioning contract:

- Version N fingerprints may only be directly compared to other version N fingerprints.
- When comparing a version N fingerprint to a version M fingerprint (N ≠ M), only dimensions present in both versions participate in the similarity computation. Dimensions present in one version but not the other are treated as null by the null-dimension rule.
- If the set of shared dimensions is empty, the comparison returns `similarity=0, dimensions_used=0` and the comparison is not used for campaign assignment.
- The fingerprint version is incremented when any feature's computation algorithm changes in a way that produces materially different values for the same input events. Adding a new feature dimension increments the version. Fixing a bug in an existing dimension increments the version. Changing the output format without changing values does not increment the version.
- A `fingerprint_version_migrations` document records each version increment: what changed, why, and whether old records can be upgraded via a migration script.

If Phase 6 adds the `fingerprint_history` table without adding new fingerprint features, the version remains at its current value and this contract is declarative but immediately effective.

### §11.5 Uncertain association review queue

`DECISION_UNCERTAIN_ASSOCIATION` observations are currently stored in `campaign_observations.notes` but not prominently surfaced. An operator who reviews a campaign's observation list sees all associations at the same visual weight, regardless of whether they were automatic or uncertain.

Phase 6 must surface this distinction:

- Campaign detail API response includes an `uncertain_observation_count` field alongside `observation_count`.
- `GET /api/campaigns/{id}/uncertain-observations` returns only the observations with uncertain decision labels.
- The dashboard campaign detail row shows a "Needs Review: N uncertain" indicator when `uncertain_observation_count > 0`.
- An analyst can annotate an uncertain observation as `analyst_confirmed` or `analyst_denied`. Confirmed observations update no data records — they record the analyst's opinion. Denied observations do not remove the campaign membership (the deterministic clustering result stands) but they flag the association as disputed for future analysis.
- AI summary prompts include uncertain_observation_count in the data block so the AI can qualify its conclusions appropriately.

---

## §12 Actor Identity Evolution Direction

### §12.1 The campaign-to-actor gap

A campaign is an observation window: a cluster of IPs with similar behavioral fingerprints, observed within a recognizable time frame. An actor is a persistent operational entity that may run multiple campaigns over years, potentially simultaneously, with different infrastructure and gradually evolved tooling.

The current data model has no actor concept. Campaign SWIFT-JACKAL-14 and campaign AMBER-WOLF-03 may be operated by the same threat actor — an inference the system cannot currently represent. When Phase 7 introduces federation, cross-operator campaign correlation will require an actor identity layer to answer "is the campaign observed by operator A the same actor as the campaign observed by operator B?"

### §12.2 Phase 6 responsibility: design and schema preparation, not full implementation

Phase 6 prepares the actor identity schema. Phase 7 implements the cross-deployment correlation and federation-aware actor merging.

The schema additions designed and migrated in Phase 6:

**`campaign_lineage` table:** Records parent-child relationships between campaigns determined to be the same actor.

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID, PK | Record identity |
| `parent_campaign_id` | UUID, FK | The earlier campaign |
| `child_campaign_id` | UUID, FK | The later campaign determined to be the same actor |
| `link_type` | string | `temporal_continuity`, `behavioral_match`, `analyst_merge`, `federation_match` |
| `similarity_score` | float | The behavioral similarity score that supported the link |
| `analyst_confirmed` | boolean | Whether an operator has confirmed this lineage link |
| `created_at` | timestamp | When the link was created |
| `notes` | JSON | Per-dimension similarity scores supporting the link |

**`actor_profiles` table (stub):** A persistent identity anchor above the campaign level. Phase 6 creates the table. Phase 7 populates it via federation-aware correlation.

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID, PK | Stable actor identity |
| `name` | string | Operator-assigned or system-generated label |
| `confidence` | float | Confidence that the linked campaigns represent one actor |
| `first_observed` | timestamp | Earliest campaign first_seen across all linked campaigns |
| `last_observed` | timestamp | Most recent activity across all linked campaigns |
| `behavioral_stability_score` | float | Stability of behavioral features across linked campaigns |
| `capability_categories` | JSON | Aggregated capability categories observed |
| `created_at` | timestamp | When this actor profile was created |

Campaign-to-actor association is recorded via a `campaign_actor_memberships` join table. API endpoints for these tables return empty results in Phase 6; they are populated in Phase 7.

### §12.3 Why design now

Retrofitting actor identity onto a mature campaign data model after Phase 7 federation introduces cross-deployment correlation would require a schema migration against live data with external dependencies. Designing the tables in Phase 6 — when they're empty and no external system depends on them — costs one empty-table migration and nothing else.

---

## §13 Similarity Infrastructure Scaling

### §13.1 The O(n) clustering bottleneck

For each new fingerprint, the clustering function queries the most-recently-active member for each active campaign, then fetches that member's fingerprint, then computes similarity. This is two SQL queries per active campaign per clustering call. The Phase 4 closeout identified the ceiling at approximately 1,000 active campaigns, at which point clustering call latency grows proportionally to campaign count.

Phase 6 must resolve this before active campaign counts can approach the ceiling.

### §13.2 Campaign fingerprint denormalization

A `representative_fingerprint_json` column is added to the `campaigns` table, storing the current behavioral vector used for candidate comparison. The fingerprint computation job updates this column when a new fingerprint is associated with the campaign.

With this column in place, the clustering query to assemble the candidate set changes from N queries (one per campaign) to a single query returning all active campaigns with their representative fingerprints in one result set. This eliminates the O(n) query pattern.

The representative fingerprint is always the most-recently-active member's fingerprint. It is not a merged or averaged fingerprint — averaging across members would obscure behavioral variation within a campaign. It is a pointer to the current behavioral representative.

### §13.3 Categorical pre-filtering

Before the full similarity computation runs (JSD on histograms, normalized Levenshtein on sequences, Jaccard on port sets), a categorical pre-filter eliminates structurally incompatible candidates.

The pre-filter operates on three fast-to-compare categorical dimensions extracted from the representative fingerprint:

- **Timing distribution class:** `periodic`, `burst`, `irregular`. A `periodic` fingerprint cannot plausibly match a `burst` fingerprint; the JSD and interval distance will be near zero regardless of other dimensions.
- **Primary protocol:** `SSH`, `HTTP`, `database`, `IoT`, `mixed`. A pure SSH scanner is unlikely to match an HTTP-focused campaign.
- **Targeting category:** `credential-brute-force`, `port-scan`, `service-enumeration`, `mixed`. Derived from the campaign's `attack_tactic_dist`.

These three categorical dimensions are stored as indexed columns on `campaigns` (derived from `representative_fingerprint_json` when it is updated). The pre-filter SQL query uses these columns to exclude structurally incompatible candidates before the expensive Python-level similarity computation runs. The surviving candidates are passed to the full similarity function.

The pre-filter is purely an optimization. It does not change which campaigns are ultimately selected — a campaign that passes the pre-filter but scores below the similarity threshold is still rejected. The pre-filter only reduces the number of candidates that reach the expensive computation step.

### §13.4 Why pgvector is deferred to Phase 7+

The instinct to use pgvector for behavioral similarity search is architecturally seductive but wrong for Phase 6 scale. The reasons are structural, not just scale-related.

**The similarity function is not a vector distance.** LegionTrap's similarity computation is a weighted combination of domain-specific metrics: Jensen-Shannon divergence on timing histograms, normalized Levenshtein edit distance on port and event-type sequences, Jaccard similarity on port sets, statistical distance on credential distributions. These do not map cleanly to cosine similarity, L2 distance, or inner product — the distances that pgvector's approximate nearest-neighbor search supports. Using pgvector would require projecting behavioral features into a fixed-length embedding space that preserves the semantic similarity structure, which requires a learned embedding model, which requires labeled training data, which does not exist.

**Per-dimension explainability would be lost.** The current similarity function returns decomposed per-dimension scores: "timing matched at 0.87, sequence matched at 0.62, credential dimension absent." This decomposition is load-bearing for operator trust and explainability. Every campaign association record stores this decomposition in `campaign_observations.notes`. A pgvector cosine score returns a single number with no semantic decomposition. Converting to vector similarity trades explainability for speed — a trade that is wrong for this system.

**Phase 6 scale does not require it.** The denormalization and categorical pre-filter described above will handle tens of thousands of active campaigns on SQLite or PostgreSQL without requiring vector infrastructure. Vector search becomes relevant when campaign counts are in the high tens of thousands and fingerprint dimensionality is high enough that categorical pre-filtering leaves too many candidates for full comparison. This is not a Phase 6 concern by any reasonable growth estimate.

**A vector-ready architecture is the correct goal.** The behavioral fingerprint features are already stored in structured JSON columns that could be projected into a fixed-length vector if needed. The similarity computation is already isolated in `app/intelligence/similarity.py` as a pure function. These properties mean a future vector embedding approach could substitute for the Levenshtein + JSD approach without touching clustering or router code. That architectural boundary should be maintained. The substitution itself belongs in a phase when measured performance data justifies the complexity.

### §13.5 Measured performance expectations

| Campaign count | Expected clustering latency (after Phase 6 optimizations) | Action trigger |
|---|---|---|
| < 1,000 | < 100ms | None |
| 1,000 – 5,000 | 100ms – 500ms | Monitor; no action |
| 5,000 – 20,000 | 500ms – 2,000ms | Evaluate categorical pre-filter refinement |
| > 20,000 | > 2,000ms | Evaluate PostgreSQL migration; evaluate further indexing |
| > 100,000 | Not specified | Architecture re-evaluation point; vector infrastructure may be justified |

---

## §14 SQLite → PostgreSQL Migration Trigger Philosophy

The current SQLite deployment is correct and sufficient for Phase 6 expected scale. The schema is PostgreSQL-compatible by design. The migration procedure exists in `docs/MIGRATION_GUIDE.md`. What does not exist is a defined trigger condition — at what point does the migration become necessary?

Phase 6 must define explicit trigger thresholds so the migration is a planned event, not an emergency response to degraded production performance.

### §14.1 Migration triggers

Any of the following conditions indicates that PostgreSQL migration should be planned and scheduled:

| Trigger | Threshold | Rationale |
|---|---|---|
| Concurrent write rate | > 50 ingest events/second sustained | SQLite WAL mode checkpoint stalls under sustained write pressure |
| Active campaign count | > 10,000 | JSON column analytics queries slow on SQLite at this scale |
| `ai_outputs` table size | > 500,000 rows | Full-table scans for reporting queries become expensive |
| Planned multi-node deployment | Any | SQLite is single-file; multi-node requires shared state |
| Multi-worker gunicorn deployment with shared write sessions | Any | SQLite WAL supports concurrent reads but single-writer contention |
| Regulatory requirement for managed DB service | Any | Compliance requirement for RDS, Cloud SQL, or equivalent |

### §14.2 Migration planning principle

When a trigger condition is observed, the migration is scheduled for the next planned maintenance window — not the next PR, and not an emergency fix. The migration itself is a documented procedure tested against a staging copy of production data. It requires operator preparation: a maintenance window, a verified backup, a rollback plan, and post-migration validation of all API endpoints.

Phase 6 should not add abstractions that claim to make the migration transparent. Migrations are not transparent. They require explicit preparation and operator action. The right approach is a well-documented, well-tested migration procedure.

---

## §15 AI Drift Prevention Principles

"AI theater" is the failure state where AI-generated outputs look authoritative, operators treat them as ground truth, and the deterministic evidence that grounded them becomes invisible. Phase 6 persistence creates conditions where theater becomes possible for the first time: stored outputs will accumulate an appearance of authority over time.

These principles are the structural defenses against theater:

**Principle 1: AI never summarizes AI.** Brief prompts consume raw campaign data. Summary prompts consume fingerprint and observation data. No prompt template may be modified to include stored AI output as context. This rule applies forever, not just in Phase 6.

**Principle 2: Stored outputs are presented with their data context, always.** When the output history panel shows a stored summary, the campaign's current deterministic state is shown alongside it. The operator can see: "this summary was generated when confidence was 0.72 with 5 observations; current state is confidence 0.89 with 12 observations." Stored outputs shown in isolation — detached from the live campaign state — are prohibited by design.

**Principle 3: Data quality scores are as prominent as AI content.** The `data_quality_score` column exists on `ai_outputs` specifically so the UI can render "Generated from sparse data — 2 observations, 3 of 5 fingerprint dimensions populated" alongside a summary with the same visual weight as the summary text. A confident-sounding AI summary over thin data is theater. The data quality score is the antidote.

**Principle 4: Regeneration is always available and always required for current intelligence.** The dashboard must provide a "Regenerate" button that triggers a new job. It must be clear that the stored output is a historical snapshot, not a live assessment. The UX design must never leave an operator uncertain about whether they are reading current or historical intelligence.

**Principle 5: AI confidence framing is always inferential, never assertional.** Prompts continue to instruct the model to use "possible," "may indicate," and "data insufficient" language. The system prompt is a constant, not configurable by operators. No Phase 6 change may weaken the uncertainty language requirement in the prompt templates.

---

## §16 Deferred, Dangerous, and Phase 7+ Items

### §16.1 Explicitly deferred from Phase 6

These items are valid and anticipated but are explicitly out of Phase 6 scope. They are deferred because the infrastructure they require does not yet exist, not because they are undesirable.

| Item | Deferred because | Next phase |
|---|---|---|
| Conversational analyst interface | Requires session state management, conversation persistence, and a free-form query model over the behavioral DB | Phase 8+ |
| Automated alerting (webhook/email/Telegram) | Requires alert deduplication, operator-tunable thresholds, and AI output quality validation at production maturity | Phase 7 |
| AI output recall via search | Requires full-text search or embedding-based retrieval over `ai_outputs`; operational need not yet established | Phase 7 |
| Actor profile population | Schema designed in Phase 6; requires federation for cross-deployment correlation to be meaningful | Phase 7 |
| Federation bilateral exchange | Requires stable fingerprint serialization format, actor identity concept, and signing infrastructure | Phase 7 |
| Threat hunting via similarity search | Requires fingerprint index optimizations to be complete and proven | Phase 7 |
| Multi-agent AI pipeline | Requires async job framework to be mature and proven; orchestration complexity premature | Phase 8+ |

### §16.2 Dangerous ideas that must not be built

These are architecturally or operationally harmful ideas. They are listed explicitly because they are frequently proposed and will be proposed again.

| Idea | Why it must not be built |
|---|---|
| AI-triggered campaign lifecycle transitions | Corrupts the deterministic-first invariant; introduces non-auditable state changes |
| AI suggestions for operator approval to trigger transitions | Same risk; the approval layer does not make it deterministic |
| AI involvement in campaign membership decisions | AI-assigned membership is neither deterministic nor auditable; corrupts downstream exports and federation |
| AI consuming previously generated AI summaries as prompt context | Recursive hallucination amplification; each iteration drifts further from deterministic ground truth |
| AI-generated IOC export content | Exports must be independently verifiable; AI-augmented exports cannot be verified without re-running the AI call |
| A "confidence" score on AI outputs derived from the AI model's tone | AI models are not calibrated probability estimators; confidence must come from deterministic data quality, not from model affect |
| AI attribution claims against named threat groups | Creates confirmation bias feedback loops; operators begin to attribute without independent verification |
| "SOC copilot" conversational interface | Reframes the AI layer as an autonomous analyst rather than an interpretation tool; erodes operator agency |
| Training data collection from production AI outputs | Requires separate data governance, consent mechanisms, and regulatory treatment; must not be conflated with operational output storage |
| Autonomous brief generation on a schedule | AI generation without operator triggering is surveillance-mode AI; no operator approval, no accountability anchor |

### §16.3 Items that belong in Phase 7+

| Capability | Earliest phase |
|---|---|
| Federation fingerprint serialization and bilateral exchange | Phase 7 |
| Actor profile population via cross-campaign behavioral correlation | Phase 7 |
| Automated alerting infrastructure (lifecycle-triggered, not AI-triggered) | Phase 7 |
| Threat hunting via similarity index | Phase 7 |
| pgvector or vector embedding for similarity search | Phase 7+ (only when measured performance data justifies it) |
| Metamorphic detection via longitudinal fingerprint drift analysis | Phase 7 (data collection begins in Phase 6) |
| Conversational analyst interface | Phase 8+ |
| Multi-agent AI orchestration | Phase 8+ |
| Deception capability (session tracking, policy engine, response generation) | Phase 8+ |
| Public behavioral fingerprint commons | Phase 9+ (requires differential privacy guarantees and legal review) |

---

## §17 Deception Separation Principles

Deception capabilities (fake credentials in responses, artificial delays, decoy routes, false service banners) are not Phase 6 work. They are Phase 8+ work. This section records the architectural separation principles that must be in place before any deception work begins, so that when the time comes, the separation is already designed.

### §17.1 Why deception must be a completely separate module

Phase 5's AI safety architecture rests on a single assumption: AI outputs are read-only analytical artifacts for operators. The safety layer — IP-in-output rejection, injection pattern detection, length limits — is designed to protect operators from receiving harmful content in AI responses. Deception inverts this relationship: the AI output goes to the adversary, not the operator.

This inversion has architectural implications that make shared infrastructure between analytical AI and deception AI dangerous:

- The IP-in-output rejection in `app/ai/safety.py` is designed to prevent IP addresses from appearing in operator-facing summaries. A deception system that refuses to include IP addresses in fake service banners is useless.
- The hallucination risk profile is inverted: for analytical outputs, hallucinations mislead operators; for deception outputs, hallucinations might produce tactically useful false information or might cause unexpected adversary behavior with legal implications.
- The audit model for deception must record both the adversary's request and the system's response — a fundamentally different audit structure from the job-level metadata tracking used for analytical outputs.

**`app/ai` is for operator-facing analytical intelligence. `app/deception` (future) is for adversary-facing response generation.** The two modules share the `AIBackend` abstraction (a general-purpose `generate()` interface) but nothing else: no prompt builders, no safety layers, no response envelopes, no output persistence tables.

### §17.2 Prerequisites for deception that do not yet exist

1. **Session tracking.** Effective deception requires maintaining context across a full attacker session. The current schema has no session concept. A `sessions` table (IP, start_time, end_time, event_ids, session_state) is the prerequisite infrastructure.

2. **A deterministic policy engine.** Which campaigns trigger deception? At what confidence threshold? What deception type? These decisions must be deterministic, auditable, and operator-configured. AI generates deception content under policy direction; it does not make policy decisions.

3. **A deception audit model.** Every generated deception response must be logged with the full session context, the adversary's request, the policy rule that triggered it, and the generated response. This is a higher audit standard than analytical outputs.

4. **Legal review.** Active deception is governed by laws that vary by jurisdiction. Some jurisdictions treat feeding false information to an adversary — even a malicious one — as legally complex in the context of the operator's infrastructure. Legal review must precede any deception implementation.

---

## §18 Phase 7 Preparation Requirements

Phase 6 must leave Phase 7 in a better position than Phase 5 left Phase 6. Three specific preparations:

**Preparation 1: Actor identity schema is in place.** The `campaign_lineage` and `actor_profiles` tables are migrated as empty tables with complete column definitions. Phase 7 federation requires stable actor identity; designing these tables during federation implementation means retrofitting schema against live data. Design them now, while they're empty.

**Preparation 2: Fingerprint versioning contract is defined and documented.** Federation will send and receive fingerprints from external deployments running different versions of the extraction code. Cross-version comparison semantics must be defined before federation begins, not during federation implementation.

**Preparation 3: Behavioral stability baseline data begins accumulating.** Metamorphic detection — identifying that an actor has deliberately shifted their behavioral signature — requires a historical baseline. The baseline is built from `fingerprint_history` records. The longer Phase 6 collects history before Phase 7 attempts to analyze it, the richer the baseline. Collecting history in Phase 6 with no immediate use for it is the correct preparation.

**Preparation 4: A Phase 7 blueprint foundation document.** Phase 6's close-out PR (Group D) should include a preliminary Phase 7 architecture document covering: federation fingerprint serialization format specification, actor profile population algorithm design, and the bilateral exchange API contract. This document does not commit to an implementation timeline; it defines the design constraints that Phase 7 must respect.

---

## §19 PR Sequencing

Phase 6 is organized into four groups. Group A ships as a complete block before Group C begins. Group B can proceed concurrently with Group C after Group A is complete. Group D closes the phase.

### Group A — Infrastructure Foundation

**PR A1: Processing jobs table, async job framework, and clustering deduplication**

This is the first and highest-priority Phase 6 PR. It closes the `_pending_ips` in-memory deduplication bug, establishes the async execution foundation, and introduces the `job_id` API contract.

Scope:
- Schema migration: `processing_jobs` table as defined in §7.2
- Replace `_pending_ips` in-memory set with database-backed job deduplication in the fingerprint/clustering background task
- Modify `POST /api/campaigns/{id}/summary` and `POST /api/campaigns/brief` to enqueue jobs and return HTTP 202 with `job_id`
- Add `GET /api/jobs/{job_id}` and `GET /api/jobs/{job_id}/result` endpoints
- Update `CampaignAiPanel` in the dashboard to poll the job endpoint rather than blocking on POST
- Implement job TTL enforcement: jobs in `running` state for longer than `AI_TIMEOUT_SECONDS × 2` are transitioned to `timed_out`
- Tests: unit tests for job lifecycle state machine; integration tests for 202 response shape, polling endpoint, TTL enforcement

**PR A2: AI output persistence**

Scope:
- Schema migration: `ai_outputs` table as defined in §8.2
- Modify the job executor to write completed outputs to `ai_outputs` before marking the job complete
- Add `GET /api/campaigns/{id}/summaries` to list stored AI outputs for a campaign (newest first)
- Add `GET /api/ai-outputs/{id}` for direct output retrieval
- Add `GET /api/ai-outputs/{id}/provenance` for provenance chain traversal
- Compute and store `data_quality_score` at execution time
- Tests: verify write-once semantics; verify provenance chain completeness; verify data_quality_score computation; verify that duplicate jobs for the same campaign produce separate records (not overwrites)

**PR A3: AI audit logging and per-key rate limiting**

Scope:
- Schema migration: `ai_audit_log` table as defined in §9.2
- Log every AI backend call from the job executor: timestamp, job_id, ai_output_id, backend, model, payload_bytes, response_bytes, latency_ms, status, error_type, operator_identity
- Implement `AI_MAX_REQUESTS_PER_MINUTE` rate limit per API key, enforced at the POST endpoint
- Add HTTP 429 response with `Retry-After` header when rate limit is exceeded
- Log rate limit events to `ai_audit_log` with `status: rate_limited`
- Add `GET /api/admin/ai-audit` endpoint (API key only) with time range, backend, status, and operator filters
- Tests: verify audit record created for every backend call; verify audit record created for failures; verify rate limiting behavior; verify rate limit events are logged

### Group B — Behavioral Memory Depth

Group B can begin after Group A is complete. Group B PRs are independent of each other and can proceed concurrently with Group C after Group A ships.

**PR B1: Campaign fingerprint denormalization and categorical pre-filter**

Scope:
- Schema migration: `representative_fingerprint_json`, `timing_class`, `primary_protocol`, `targeting_category` columns on `campaigns` table
- Update fingerprint computation job to populate these columns when a new fingerprint is associated with a campaign
- Modify clustering candidate query to use the new columns instead of N per-campaign member queries
- Add categorical pre-filter step before full similarity computation
- Benchmark clustering latency before and after the change and record results in the PR description
- Tests: verify clustering produces identical results before and after the optimization; verify pre-filter does not produce false exclusions for known-matching fingerprints

**PR B2: Fingerprint history table and behavioral stability score**

Scope:
- Schema migration: `fingerprint_history` table as defined in §11.2
- Schema migration: `behavioral_stability_score` column on `campaigns` table
- Modify fingerprint computation job to append to `fingerprint_history` in addition to updating `behavioral_fingerprints`
- Implement behavioral stability score computation: per-dimension stability as inverse variance across history records; composite score using similarity weights
- Update `behavioral_stability_score` on `campaigns` after each fingerprint history append
- Add `GET /api/campaigns/{id}/fingerprint-history` API endpoint
- Include `behavioral_stability_score` and `uncertain_observation_count` in campaign detail API response and in prompt builder context
- Tests: verify history records accumulate without overwriting; verify stability score computation against known history fixtures; verify stability score decreases when behavioral drift is introduced

**PR B3: Fingerprint versioning contract**

Scope:
- Document the fingerprint versioning contract in `docs/` (a `FINGERPRINT_VERSIONING.md` document)
- Add version compatibility enforcement in `app/intelligence/similarity.py`: cross-version comparisons use only shared dimensions; empty shared dimension set returns similarity 0
- Add tests for cross-version comparison semantics
- If Phase 6 does not add new fingerprint features, this PR is documentation and tests only; no schema migration required

**PR B4: Uncertain association review queue**

Scope:
- Add `uncertain_observation_count` to campaign detail API response (count of observations with `DECISION_UNCERTAIN_ASSOCIATION` in notes)
- Add `GET /api/campaigns/{id}/uncertain-observations` endpoint
- Add analyst annotation: `POST /api/campaign-observations/{id}/annotate` with body `{decision: "analyst_confirmed" | "analyst_denied", notes: string}` — stores the analyst opinion without modifying the original clustering decision
- Dashboard: "Needs Review: N" indicator on campaigns with unreviewed uncertain observations
- Dashboard: uncertain observations marked visually distinct from automatic associations in the observation list
- AI summary prompt includes `uncertain_observation_count` in the data block
- Tests: verify uncertain observations are correctly counted and returned; verify analyst annotation stores opinion without modifying original clustering record

### Group C — AI Feature Expansion

Group C begins after Group A is complete. Group B and Group C can proceed concurrently.

**PR C1: Multi-campaign brief with time window parameter**

Scope:
- Add optional `time_window_start` and `time_window_end` parameters to `BriefRequest`
- When time window is provided, filter campaigns by `last_seen BETWEEN time_window_start AND time_window_end` instead of (or in addition to) status filter
- Status filter and time window filter are combinable; both are optional independently; when neither is specified, current behavior (status filter only) applies
- Update `POST /api/campaigns/brief` to return 202 with job_id (using the async contract from PR A1)
- Update brief prompt builder to include the time window in the prompt context when provided
- Tests: verify time-windowed brief includes only campaigns with last_seen in the window; verify status + time window combination; verify response envelope shape

**PR C2: Brief dashboard panel**

Scope:
- Add a "Threat Brief" panel to the dashboard, operator-triggered ("Generate Threat Brief" button)
- The panel follows the same pattern as `CampaignAiPanel`: warning banner always visible, operator-triggered only, plain text output, never auto-generates
- Brief panel shows `campaign_count`, `source_records.campaign_ids` as attribution metadata alongside the brief text
- Dashboard polls the job endpoint for brief job completion (using the polling model from PR A1)
- Optional: time window parameters exposed in the UI as a date range picker
- Tests: verify panel renders warning banner; verify polling behavior; verify attribution metadata is displayed

**PR C3: AI output history panel**

Scope:
- Add an output history view within the campaign detail, accessible from the existing `CampaignAiPanel`
- Retrieves stored outputs from `GET /api/campaigns/{id}/summaries`
- Each stored output shows: `generated_at` timestamp prominently, AI backend and model name, data quality score, content (or rejection reason), source records summary
- Campaign's current deterministic state is shown alongside each historical output for comparison
- "Regenerate" button triggers a new job; the new output is added to the history; old outputs remain unchanged
- Tests: verify history panel renders all stored outputs; verify current campaign state is shown alongside each historical output; verify regeneration creates a new record without modifying existing records

### Group D — Phase 7 Preparation and Close-Out

**PR D1: Actor identity schema preparation**

Scope:
- Schema migration: `campaign_lineage` table as defined in §12.2
- Schema migration: `actor_profiles` table (stub columns) as defined in §12.2
- Schema migration: `campaign_actor_memberships` join table
- API stubs: `GET /api/actors` returns empty list; `GET /api/actors/{id}` returns 404; `GET /api/actors/{id}/campaigns` returns empty list
- These stubs establish the API contract that Phase 7 will populate
- Tests: verify migrations complete without error; verify API stubs return correct empty responses; verify no existing functionality is affected

**PR D2: Phase 6 close-out documentation**

Scope:
- `docs/PHASE_6_CLOSEOUT.md` — full delivery record, architectural changes, deferred items, known limitations, operational risks, testing summary, Phase 7 direction
- `docs/PHASE_7_FOUNDATION.md` — preliminary Phase 7 architecture document: federation fingerprint serialization format specification, actor profile population algorithm design, bilateral exchange API contract (does not commit to implementation timeline)
- Updates to `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `README.md`
- `docs/PHASE_6_BLUEPRINT.md` status updated to Implemented

---

## §20 Testing Strategy

### Unit tests

| Test file | Coverage |
|---|---|
| `tests/unit/test_processing_jobs.py` | Job lifecycle state machine; TTL enforcement; deduplication logic |
| `tests/unit/test_ai_persistence.py` | Write-once semantics; data_quality_score computation; prompt_hash derivation; provenance chain construction |
| `tests/unit/test_audit_logging.py` | Audit record shape; content exclusion; rate limit event logging |
| `tests/unit/test_fingerprint_history.py` | History record accumulation; stability score computation; cross-version comparison semantics |
| `tests/unit/test_similarity_prefilter.py` | Categorical pre-filter correctness: no false exclusions for known-matching fingerprints; false positives acceptable (more candidates) |

### Integration tests

| Test file | Coverage |
|---|---|
| `tests/integration/test_async_endpoints.py` | POST returns 202 with job_id; GET /jobs/{id} polling lifecycle; result retrieval on completion; TTL-expired jobs return timed_out |
| `tests/integration/test_ai_persistence_endpoints.py` | POST summary → job complete → ai_output record exists; GET /campaigns/{id}/summaries returns history; regeneration appends, not overwrites |
| `tests/integration/test_ai_audit.py` | Every successful AI call produces an audit record; every failed call produces an audit record; rate limiting produces 429 and audit record |
| `tests/integration/test_clustering_performance.py` | Clustering with denormalized fingerprints produces same results as before denormalization; latency benchmark at N=100, N=1000 campaigns |
| `tests/integration/test_fingerprint_history.py` | Each fingerprint computation appends to history; stability score updates after each append; history is never overwritten |
| `tests/integration/test_uncertain_observations.py` | Uncertain observation count is correct; analyst annotation stores opinion without modifying clustering record |

### No live AI calls in tests

All integration tests inject `MockAIBackend` via monkeypatching. No test calls the real Claude API or a real Ollama endpoint. The `ANTHROPIC_API_KEY` is not required for the test suite to pass.

### Invariant verification tests

A suite of invariant verification tests verifies that the deterministic-first invariants from §3 hold after each Phase 6 PR:

- `test_ai_modules_not_imported_in_ingest.py`: verify no `app.ai` import exists in `app/routers/ingest.py` or `app/intelligence/`
- `test_ai_output_never_in_prompt_context.py`: build prompts using fixtures that include stored AI outputs in the database; verify the built prompt contains no AI output text
- `test_no_ai_writes_to_campaign_tables.py`: after a full job execution with MockAIBackend, verify that `campaigns`, `behavioral_fingerprints`, `campaign_observations`, and `events` tables are unmodified

---

*Cross-references: [PHASE_5_CLOSEOUT.md](PHASE_5_CLOSEOUT.md) · [PHASE_5_BLUEPRINT.md](PHASE_5_BLUEPRINT.md) · [PHASE_4_CLOSEOUT.md](PHASE_4_CLOSEOUT.md) · [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [AI_ROADMAP.md](AI_ROADMAP.md) · [AI_REASONING_ARCHITECTURE.md](AI_REASONING_ARCHITECTURE.md) · [BEHAVIORAL_INTELLIGENCE.md](BEHAVIORAL_INTELLIGENCE.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
