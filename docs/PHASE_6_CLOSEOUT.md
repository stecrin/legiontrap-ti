# Phase 6 Close-Out — Behavioral Memory and Campaign Intelligence

**Document type:** Phase completion record and architectural handoff
**Audience:** Engineers, contributors
**Date:** 2026-05-28

---

## 1. What Phase 6 Delivered

Phase 6 closed the infrastructure and accountability gaps that Phase 5 left open, then deepened the behavioral memory model in preparation for Phase 7 actor-level intelligence.

Phase 5 proved that AI-assisted analysis could produce useful natural-language intelligence from structured campaign data. Phase 6 made that AI layer accountable: every output is now persisted, every API call is audited, every job is trackable, and every operator-triggered request returns immediately with a job ID. Phase 6 also extended the memory model from a point-in-time fingerprint snapshot to a longitudinal history that Phase 7 can use for drift and metamorphic detection.

### Pull Requests

| PR | Branch | Group | Title |
|----|--------|-------|-------|
| #50 | `docs/phase6-blueprint` | — | Phase 6 architecture blueprint |
| #51 | `feat/phase6-processing-jobs` | A | Processing job infrastructure and async AI workflow |
| #52 | `feat/phase6-ai-output-persistence` | A | Persist immutable AI outputs |
| #53 | `feat/phase6-ai-audit-rate-limit` | A | AI audit logging and rate limiting |
| #54 | `feat/phase6-fingerprint-history` | B | Fingerprint history and representative campaign fingerprints |
| #55 | `feat/phase6-behavioral-stability` | B | Behavioral stability scoring |
| #56 | `feat/phase6-uncertain-association-review` | B | Uncertain association review queue |
| #57 | `feat/phase6-brief-time-window` | C | Time-window campaign briefs and dashboard brief panel |
| #58 | `feat/phase6-ai-output-history` | C | Campaign AI output history panel |
| D1+D2 | `feat/phase6-closeout` | D | Actor identity schema foundations and Phase 6 close-out |

---

## 2. What Changed Architecturally

Phase 6 introduced five new database tables, four new repository modules, three new API routers, and three new dashboard components. The ingest path, clustering algorithm, export layer, and privacy model are unchanged.

**New tables (Phase 6):**

| Table | Group | Purpose |
|-------|-------|---------|
| `processing_jobs` | A | Central coordination for all async AI operations |
| `ai_outputs` | A | Immutable, write-once record of every AI-generated artifact |
| `ai_audit_log` | A | Metadata-only audit record for every external AI API call |
| `fingerprint_history` | B | Append-only longitudinal snapshots of behavioral fingerprints |
| `actor_profiles` | D | Empty foundation for Phase 7 actor-level intelligence |
| `campaign_lineage` | D | Empty foundation linking campaigns to actor profiles |

**Schema additions to existing tables:**

| Table | Column | Group | Purpose |
|-------|--------|-------|---------|
| `campaign_observations` | `analyst_review_json` | B | Analyst interpretation of uncertain associations |
| `campaigns` | `representative_fingerprint_json` | B | Cluster centroid fingerprint |
| `campaigns` | `behavioral_stability_json` | B | Longitudinal stability metrics |

**New routers:**

| File | Endpoints | Group |
|------|-----------|-------|
| `app/routers/jobs.py` | `GET /api/jobs/{job_id}`, `GET /api/jobs` | A |
| `app/routers/ai_outputs.py` | `GET /api/ai/outputs/{id}`, `GET /api/campaigns/{id}/ai-outputs` | A |
| Additions to `campaigns.py` | `GET /api/campaigns/uncertain-associations`, `POST /api/campaigns/uncertain-associations/{id}/review` | B |

**API contract change:** `POST /api/campaigns/{id}/summary` and `POST /api/campaigns/brief` changed from synchronous 200 OK to 202 Accepted with `job_id` + `poll_url`. This is a permanent, breaking change to the async contract.

**New repository modules:** `ActorRepository`, `AiAuditLogRepository`, `AiOutputRepository`, `FingerprintHistoryRepository`, `JobRepository` — all added as mixins to `EventRepository`.

---

## 3. Async/Job Infrastructure Summary

Phase 5 AI calls were synchronous and untracked. Phase 6 Group A replaced this with a permanent async contract backed by the `processing_jobs` table.

**202 Accepted contract:**
- `POST /api/campaigns/{id}/summary` returns immediately with `{ job_id, status: "pending", poll_url }`.
- `POST /api/campaigns/brief` returns immediately with the same shape.
- Callers poll `GET /api/jobs/{job_id}` until `status` reaches a terminal state: `completed` or `failed`.
- Terminal states are permanent — they never revert.

**Job execution:** FastAPI `BackgroundTasks` runs the job function in the same process after the HTTP response is sent. The runner sets `status=running` on start, `status=completed` on success with `ai_output_id` set, and `status=failed` with `error_message` on any exception.

**Deduplication:** `POST /api/campaigns/{id}/summary` checks for an existing `pending` or `running` job for the same campaign before creating a new one. If a duplicate exists, the existing `job_id` is returned immediately. No duplicate jobs are created.

**TTL enforcement:** `GET /api/jobs/{job_id}` applies a TTL check on read: a job stuck in `running` for longer than `AI_TIMEOUT_SECONDS × 2` is transitioned to `failed` before the response is built. This prevents ghost records from accumulating after process restarts.

**Rate limiting:** AI endpoints count jobs created by the same operator in the last 60 seconds via `processing_jobs`. The limit is `AI_MAX_REQUESTS_PER_MINUTE` (default: 10). Rate-limited requests write to `ai_audit_log` in a separate session before raising HTTP 429, so the audit record commits even though the main request fails.

---

## 4. AI Persistence and Audit Summary

**AI output persistence (`ai_outputs`):**

Every AI-generated artifact is written to `ai_outputs` before being returned. The table is write-once: there is no `UPDATE` or `DELETE` path. Fields include:

- `content` — the raw AI text
- `backend`, `model_name` — which AI system produced it
- `prompt_hash` — SHA-256 of the assembled prompt (for audit; prompt content is never stored)
- `source_records_json` — the specific data used as AI context
- `safety_flags_json` — any safety check results
- `rejected`, `rejection_reason` — whether the output passed safety validation
- `truncated` — whether the output exceeded the length limit
- `data_quality_score` — a 0–1 quality metric from the runner
- `generated_at`, `triggered_by` — provenance

The `ai_output_id` foreign key in `processing_jobs` links the job to its persisted result.

**AI audit logging (`ai_audit_log`):**

Every external AI API call writes a metadata-only record: timestamp, job_id, backend, model, operation type, payload bytes, response bytes, latency in milliseconds, and status. Content is never stored — only byte counts. This answers the compliance question "what data left this system and when" without reconstructing prompts.

Rate-limited requests are logged with `status=rate_limited`. Rejected outputs are logged with `status=rejected`. Every call to the AI backend produces one audit row regardless of outcome.

---

## 5. Behavioral Memory Improvements

**Fingerprint history (`fingerprint_history`):**

The `fingerprint_history` table appends a snapshot of `behavioral_fingerprints` every time a fingerprint is recomputed for a source IP. Each row is immutable and append-only. The history enables Phase 7 behavioral drift detection — comparing today's fingerprint against the fingerprint from 6 months ago to detect deliberate behavioral adaptation.

**Representative campaign fingerprints:**

The `campaigns` table gained `representative_fingerprint_json`, which stores the cluster centroid fingerprint — the most representative behavioral pattern across all member IPs. This is the reference fingerprint used for reactivation detection: an incoming fingerprint is compared against the representative fingerprint of all existing campaigns, not individual member fingerprints.

**Behavioral stability scoring:**

The `campaigns` table gained `behavioral_stability_json`, which stores longitudinal stability metrics across the dimensions tracked by the fingerprint (timing, sequence, protocol, credential, target). Stability is computed from the fingerprint history. A campaign with high stability has behaved consistently over time. A campaign with declining stability may be adapting its tooling. Both are intelligence signals.

**Uncertain association review queue:**

Clustering observations with `decision=uncertain_association` in their notes JSON are exposed via `GET /api/campaigns/uncertain-associations`. Analysts can submit `POST /api/campaigns/uncertain-associations/{id}/review` with `analyst_confirmed` or `analyst_denied` to record their interpretation. The review is stored in `analyst_review_json` on the observation row. It does not mutate campaign membership or alter the original clustering decision.

---

## 6. Dashboard and Operator-Facing Changes

**Campaign AI summary panel (inherited from Phase 5, unchanged):**
The `CampaignAiPanel` component is unchanged. It generates an in-memory AI summary for a single campaign on operator demand. No auto-generation.

**Multi-campaign threat brief panel (Phase 6 Group C — PR #57):**
The `CampaignBriefPanel` component allows an operator to request a multi-campaign threat brief with optional time-window filtering (`time_window_start`, `time_window_end`). The panel uses the async 202 contract: it submits the brief, then polls `GET /api/jobs/{job_id}` until completion. Results are displayed as plain text. No auto-generation. No markdown rendering. No localStorage persistence.

**Campaign AI output history panel (Phase 6 Group C — PR #58):**
The `CampaignAiOutputHistory` component is rendered below `CampaignAiPanel` in each campaign's expanded row. It fetches all persisted AI output records for the campaign from `GET /api/campaigns/{id}/ai-outputs` on expand. Each output card shows: `generated_at`, backend/model, quality score, rejected/truncated badges, source record counts, and plain text content. A "Regenerate Summary" button submits a new summary job and polls until completion, then refreshes the history list. A "Historical AI output" warning banner is always visible.

**New API helpers (Phase 6 Group C):**
`ui/dashboard/src/lib/api.js` gained: `postCampaignBrief`, `getJob`, `getCampaignAiOutputs`, `getAiOutput`.

---

## 7. Actor Identity Preparation

Phase 6 Group D created two empty schema foundations to enable Phase 7 actor-level intelligence without implementing actor attribution in Phase 6.

**`actor_profiles`:** One row per inferred actor identity. Fields include `display_name`, `confidence`, `status`, `representative_fingerprint_json`, `behavioral_stability_json`, `notes`, `created_at`, `updated_at`. No row is created automatically by clustering, lifecycle transitions, or AI code paths.

**`campaign_lineage`:** Links a campaign to an actor profile with an explicit `relationship_type`, `confidence`, and analyst-supplied `evidence_json`. Does not mutate campaign membership or clustering decisions.

**Repository support:** `ActorRepository` provides `create_actor_profile()`, `get_actor_profile()`, `list_actor_profiles()`, `link_campaign_to_actor()`, `list_campaign_lineage()`. All five methods are purely explicit — no automatic assignment logic exists.

**What is absent by design:**
- No automatic actor attribution from clustering
- No campaign merging or splitting
- No AI actor naming
- No API endpoints for actor profiles (deferred to Phase 7)
- No dashboard actor UI

---

## 8. What Was Intentionally Deferred

The following items were scoped, understood, and explicitly deferred from Phase 6:

**From Group A:**
- Celery or asyncio worker process (using FastAPI `BackgroundTasks`; worker replacement is an implementation swap, not an API change)
- `GET /api/jobs/{job_id}/result` convenience endpoint (callers fetch from `/api/ai/outputs/{ai_output_id}` directly)
- Job cancellation endpoint

**From Group B:**
- Bulk analyst review (single-observation review only)
- Dashboard review panel for uncertain associations
- Automated behavioral drift alerts

**From Group C:**
- Time-window filter UI on the campaign list (time window is available on the brief endpoint only)
- AI output pagination UI (backend limit=20 applies; UI shows all returned outputs)
- AI output filter by type in the history panel

**From Group D:**
- All actor attribution logic
- Actor profile API endpoints
- Campaign lineage API endpoints
- Dashboard actor UI
- Federation implementation

---

## 9. Known Limitations

**`BackgroundTasks` process model:** Jobs run in the same OS process as the HTTP server. A server restart while a job is running leaves the job in `running` state indefinitely. The TTL enforcement in `GET /api/jobs/{job_id}` mitigates this: a job stuck in `running` past `AI_TIMEOUT_SECONDS × 2` is transitioned to `failed` on first read. However, no job is retried automatically after a crash.

**SQLite write serialization:** `processing_jobs` and `ai_outputs` writes are serialized by SQLite's WAL-mode writer lock. Under concurrent AI job submissions, write latency can spike. This is acceptable for single-operator deployments and low-volume research use. High-concurrency production deployments require PostgreSQL.

**Fingerprint history is not yet used for alerting:** The `fingerprint_history` table is populated and queryable, but no automated alert fires when behavioral drift exceeds a threshold. Drift alerting is Phase 7 Group A; Phase 6 only collects the longitudinal data.

**Analyst review does not propagate:** A review decision (`analyst_confirmed` or `analyst_denied`) on an uncertain observation is stored but not surfaced to the clustering algorithm, the campaign confidence score, or any downstream consumer. Phase 7 Group A uses these signals to adjust per-campaign similarity weight profiles.

**`representative_fingerprint_json` and `behavioral_stability_json` require the analytics job:** These columns are populated by the behavioral stability scoring job. They are `NULL` for campaigns that have not yet had the job run against them. The job must be triggered manually or via the scheduled lifecycle job.

---

## 10. Phase 7 Recommended Direction

Phase 7 is named **Actor Intelligence**.

The architectural review conducted before Phase 7 planning identified that two categories of Phase 6 output are not yet used: analyst review decisions on uncertain associations, and longitudinal fingerprint drift signals. Building actor identity before closing those feedback loops would produce attribution on uncalibrated data. Phase 7 addresses this by making Group A (feedback loop closure) a hard prerequisite for Group B (actor identity).

**Group A — Feedback Loop Closure (must ship before Group B):**

1. Review decision propagation: confirmed uncertain associations adjust per-campaign similarity weight profiles. The operator can inspect current effective weights and trace them to source review decisions. This does not eliminate clustering determinism — it makes the configurable weights respond to accumulated operator judgment rather than remaining permanently static.
2. Drift alerting: configurable per-dimension thresholds on behavioral stability. Threshold crossings write to a `behavioral_alerts` table and surface in the dashboard. No automated response. The operator decides what a drift signal means.
3. Sparse campaign surface: campaigns that accumulated insufficient evidence to confirm are surfaced with a distinct lifecycle status, separate from active, dormant, and historical.

**Group B — Actor Identity (builds on Group A and Phase 6 Group D foundations):**

1. Define `relationship_type` vocabulary for `campaign_lineage` before writing any API: `primary_campaign`, `infrastructure_reuse`, `tactic_match`, `temporal_overlap`. Open strings are not accepted.
2. Implement actor profile CRUD API: `POST /api/actors`, `GET /api/actors`, `GET /api/actors/{id}`, `PATCH /api/actors/{id}`.
3. Implement `POST /api/actors/{id}/campaigns` and `GET /api/actors/{id}/campaigns` with relationship_type validation.
4. Implement actor suggestion engine: `GET /api/actors/suggestions` surfaces campaign pairs whose representative fingerprints exceed a configurable similarity threshold and have no existing lineage. Read-only. Never writes automatically. Analyst confirms or denies.
5. Implement actor-level stability view: `GET /api/actors/{id}/stability` aggregates behavioral stability across all campaigns linked to the actor.
6. Add dashboard actor profile panel — read-only view of linked campaigns, similarity suggestions, and stability trends. No automatic attribution.

**Federation is deferred to Phase 8.** Federation is not a code prerequisite problem — the fingerprint model and privacy architecture are already designed. It is an operational prerequisite problem: building the protocol before two real operators are willing to exchange fingerprints produces infrastructure that cannot be validated. Phase 8 has explicit entry criteria; it begins when those criteria are confirmed, not on a timeline.

**What must not happen in Phase 7:**
- Automatic actor attribution from clustering (humans assign actors to campaigns)
- AI actor naming (actor display names are operator-assigned)
- Merging campaigns into a single canonical record (campaigns are immutable history; lineage records the relationship)
- Any change to the clustering algorithm's core similarity logic
- Any federation implementation (belongs to Phase 8)

---

*Cross-references: [PHASE_6_BLUEPRINT.md](PHASE_6_BLUEPRINT.md) · [PHASE_5_CLOSEOUT.md](PHASE_5_CLOSEOUT.md) · [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md)*
