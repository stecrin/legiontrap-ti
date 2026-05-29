# Phase 7 Close-Out — Actor Intelligence

**Document type:** Phase completion record and architectural handoff
**Audience:** Engineers, contributors
**Date:** 2026-05-29

---

## 1. Phase 7 Mission

Phase 7 had two sequential missions.

**Mission 1 — Close the feedback loops.** Phase 6 collected two categories of operator intelligence that were stored but never consumed: analyst review decisions on uncertain clustering associations, and longitudinal behavioral drift signals in `fingerprint_history`. Building actor identity on top of uncalibrated clustering data would produce actor profiles with false precision. Phase 7 Group A closed both loops before Group B began.

**Mission 2 — Activate actor identity.** Phase 6 Group D created the `actor_profiles` and `campaign_lineage` tables and the `ActorRepository` with five methods. No API endpoints exposed them. Phase 7 Group B activated them with a CRUD API, a read-only suggestion engine, an actor-level stability view, and a dashboard panel.

The sequencing was a hard architectural constraint: Group A shipped as a complete block before any Group B work began.

---

## 2. Pull Requests

| PR | Branch | Title |
|----|--------|-------|
| #67 | `docs/phase7-blueprint` | Phase 7 architecture blueprint |
| #68 | `feat/phase7-feedback-loop-foundation` | Group A: weight profiles, drift alerting, sparse campaign surface |
| #69 | `feat/phase7-sparse-campaign-surface` | A3: sparse campaign surface |
| #70 | `feat/phase7-actor-foundation` | B1: relationship type vocabulary and actor CRUD API |
| #72 | `feat/phase7-actor-suggestion-engine` | B3: actor suggestion engine |
| #73 | `feat/phase7-actor-stability-view` | B4: actor-level stability view |
| #74 | `feat/phase7-actor-dashboard-panel` | B5: actor dashboard panel |
| #75 | `fix/phase7-actor-linking-and-suggestions` | B2: campaign-to-actor linking API; suggestion `score_breakdown` field fix |

---

## 3. Group A — Feedback Loop Closure

Group A closed the two intelligence feedback loops that Phase 6 opened but never consumed, and surfaced a third data quality signal.

### A1 — Review Decision Propagation and Weight Profiles

**New table: `campaign_weight_profiles`**

Stores per-campaign similarity weight adjustments derived from accumulated analyst reviews. Each row records the current effective weights for each of the five behavioral dimensions (timing, sequence, protocol, credential, target), review counts, and a full append-only `adjustment_log_json` tracing every weight change back to its source observation ID.

**New module: `app/intelligence/weight_profiles.py`**

`process_campaign_weight_profile(campaign_id)` reads `analyst_review_json` from `campaign_observations`, applies bounded linear nudges to the weight profile, renormalizes, and writes the result to `campaign_weight_profiles`. The adjustment algorithm is intentionally simple: a confirmed review increases weights on high-similarity dimensions; a denied review decreases them. No dimension falls below `WEIGHT_FLOOR` or exceeds `WEIGHT_CEILING`. The same observation ID is never applied twice.

`process_all_campaign_weight_profiles()` runs during the analytics job cycle.

**New endpoint: `GET /api/campaigns/{id}/weight-profile`**

Returns the current effective weights, the global defaults they diverged from, review counts, the full adjustment log, and a status field (`"calibrated"` or `"using_global_defaults"`). An operator can reconstruct exactly why a campaign's weight profile is what it is from this endpoint alone.

**New configuration variables:** `WEIGHT_REVIEW_NUDGE` (default 0.02), `WEIGHT_FLOOR` (default 0.05), `WEIGHT_CEILING` (default 0.60), `WEIGHT_PROFILE_MIN_REVIEWS` (default 3), `WEIGHT_HIGH_SCORE_GATE` (default 0.70).

### A2 — Behavioral Drift Alerting

**New table: `behavioral_alerts`**

Stores threshold crossing records for behavioral stability. Each row records the campaign, alert type (`composite_drift` or `dimension_drift`), the specific dimension (null for composite), the configured threshold, the observed value, a snapshot of the full stability JSON at trigger time, and acknowledgement state.

**New module: `app/intelligence/drift_alerts.py`**

`check_campaign_drift_alerts(campaign_id)` reads a campaign's `behavioral_stability_json`, compares each score against per-dimension thresholds, and writes to `behavioral_alerts` when a threshold is crossed. Deduplication prevents alert storms: a new alert is not inserted when an unacknowledged alert already exists for the same campaign and dimension. Acknowledged alerts do not block new alerts. Campaigns with `status = "insufficient_data"` produce no alerts.

`check_all_campaign_drift_alerts()` runs during the analytics job cycle.

**New router: `app/routers/alerts.py`**

- `GET /api/alerts` — list unacknowledged alerts; optional `campaign_id` filter and `include_acknowledged` param
- `POST /api/alerts/{id}/acknowledge` — mark acknowledged with optional notes
- `GET /api/campaigns/{id}/alerts` — all alerts for a specific campaign

Acknowledgement records operator awareness. It does not modify campaigns, fingerprints, weight profiles, or clustering decisions.

**New configuration variables:** `DRIFT_ALERT_COMPOSITE_THRESHOLD` (default 0.65), plus per-dimension thresholds for timing, sequence, protocol, credential, and target dimensions.

### A3 — Sparse Campaign Surface

**New endpoint: `GET /api/campaigns/sparse`**

Returns campaigns that have insufficient behavioral data for the analytics pipeline to produce reliable outputs: `representative_fingerprint_json IS NULL` or `event_count < MIN_EVENTS_FOR_CLUSTERING`. Campaigns are returned with event count, last seen, and status. Sparse is a query-time label, not a lifecycle state; the existing `status` column is unchanged.

No automatic action is taken. Surfacing the signal to the operator is the complete scope of A3.

---

## 4. Group B — Actor Identity

### B1 — Relationship Type Vocabulary and Actor CRUD API

**New module: `app/intelligence/actor_constants.py`**

Defines `VALID_RELATIONSHIP_TYPES: frozenset[str]` with four values:

| Type | Meaning |
|---|---|
| `primary_campaign` | Most representative campaign attributed to this actor |
| `infrastructure_reuse` | Shared infrastructure (ASN, timing) without matching probe sequences |
| `tactic_match` | Shared attack tactics and protocol behavior observed separately |
| `temporal_overlap` | Active during the same window, sharing a subset of behavioral dimensions |

Open strings are not accepted. `ActorRepository.link_campaign_to_actor()` raises `ValueError` on an unrecognized type; the router returns HTTP 422.

**New router: `app/routers/actors.py`**

- `POST /api/actors` — create actor profile (HTTP 201); all fields are operator-supplied; no automatic attribution
- `GET /api/actors` — list profiles ordered by `created_at DESC`; optional `status` filter and `limit` param
- `GET /api/actors/{id}` — single profile; 404 if not found
- `PATCH /api/actors/{id}` — partial update of `display_name`, `notes`, `confidence`, `status`; uses `model_fields_set` to distinguish fields explicitly set to null from fields omitted

Route ordering invariant: `GET /api/actors/suggestions` is registered before `GET /api/actors/{id}` to prevent `"suggestions"` being interpreted as an actor ID.

### B2 — Campaign-to-Actor Linking API

**New endpoints: `POST/GET/DELETE /api/actors/{id}/campaigns`, `GET /api/campaigns/{id}/actors`**

PR #75 completed the linking API after the initial Phase 7 delivery. Four endpoints ship in `app/routers/actors.py` and `app/routers/campaigns.py`.

`POST /api/actors/{actor_id}/campaigns` (HTTP 201) validates that the actor and campaign both exist before inserting a `campaign_lineage` row. `relationship_type` is validated against `VALID_RELATIONSHIP_TYPES`. A duplicate actor/campaign pair returns HTTP 409. No automatic attribution occurs — this is an explicit operator action. Only `campaign_lineage` is written; `actor_profiles` and `campaigns` are never modified.

`GET /api/actors/{actor_id}/campaigns` returns linked campaigns with `campaign_lineage` metadata (lineage_id, relationship_type, confidence, linked_at) joined with campaign name, status, and last_seen. 404 if the actor does not exist.

`DELETE /api/actors/{actor_id}/campaigns/{lineage_id}` (HTTP 204) performs a hard delete on the `campaign_lineage` row. Returns 404 if the lineage record does not exist or belongs to a different actor. Campaigns and actor profiles are not touched.

`GET /api/campaigns/{campaign_id}/actors` returns actors linked to a campaign with actor profile metadata (display_name, status, confidence). 404 if the campaign does not exist. Read-only.

**New repository methods** added to `app/db/repositories/actor.py`: `get_lineage_row()`, `delete_lineage_row()`, `list_actor_campaigns_with_metadata()`, `list_actors_for_campaign()`.

**`score_breakdown` field fix** (also in PR #75): `build_actor_suggestions()` previously returned `"breakdown"` in each suggestion dict; the dashboard and all tests now consistently use `"score_breakdown"`.

**New API function** added to `ui/dashboard/src/lib/api.js`: the `ActorPanel.jsx` suggestions already rendered a `score_breakdown` key; the backend key was aligned to match.

### B3 — Actor Suggestion Engine

**New module: `app/intelligence/actor_suggestions.py`**

Pure computation: no database access, no I/O, no side effects.

`build_actor_suggestions(campaigns, coattributed_pairs, *, min_score, limit)` iterates all pairs from `list_campaigns_for_suggestions()` (campaigns with a non-null `representative_fingerprint_json` and status in active/dormant/reactivated), skips pairs already co-attributed under a common actor, computes `compute_weighted_similarity()` for each remaining pair, and returns pairs above `min_score` sorted descending.

An advisory `suggested_relationship_type` hint is derived per pair from which dimensions drove the match:
- `sequence >= 0.85` AND `timing >= 0.80` → `primary_campaign`
- `timing >= 0.80` AND `sequence < 0.70` → `infrastructure_reuse`
- `protocol >= 0.80` → `tactic_match`
- otherwise → `temporal_overlap`

The hint is a label in the response. It is never written to any table automatically.

**New endpoint: `GET /api/actors/suggestions`**

Query params: `min_score` (optional float override), `limit` (optional, default 20, max 100).

Returns: `suggestions`, `count`, `total_pairs_evaluated`, `min_score_applied`, `campaigns_evaluated`. This endpoint is strictly read-only. It never writes to actor_profiles, campaign_lineage, campaigns, or any other table.

**New configuration variables:** `ACTOR_SUGGESTION_MIN_SCORE` (default 0.85), `ACTOR_SUGGESTION_LIMIT` (default 20).

### B4 — Actor-Level Stability View

**New module: `app/intelligence/actor_stability.py`**

Pure computation: no database access, no I/O, no side effects.

`aggregate_actor_stability(campaign_rows)` reads `behavioral_stability_json` from each campaign row linked to an actor, separates campaigns with usable data from those with null or `insufficient_data` stability, computes min/max/mean across composite and per-dimension scores for the usable set, and returns the full aggregation with a `contributors` list that includes every linked campaign — including those with null stability.

Status ladder: `no_linked_campaigns` → `no_stability_data` → `partial_data` → `ok`.

**New endpoint: `GET /api/actors/{id}/stability`**

Returns: `actor_id`, `actor_display_name`, `linked_campaign_count`, `campaigns_with_stability`, `campaigns_missing_stability`, `actor_composite_stability` (min/max/mean or null), `dimension_stability` (per-dimension min/max/mean or null), `contributors`, `status`, `computed_at`. Read-only; no data is written. 404 if actor does not exist.

### B5 — Actor Dashboard Panel

**New component: `ui/dashboard/src/components/ActorPanel.jsx`**

Registered in `App.jsx` after the `Campaigns` panel. Takes a `dark` prop for theme.

**Actor Profiles section:** Table listing all actor profiles with display name, status badge, confidence bar, notes (truncated), created/updated timestamps. Click to expand; expanded rows fetch and display stability data on demand — composite score, per-dimension stability chips, and a linked campaigns table with relationship type badges.

**Review Candidates section:** Shows suggestions from `GET /api/actors/suggestions`. Labelled "Review Candidates" with subtitle text: "Suggested campaign pairs for operator review only. No automatic action is taken." Each row shows both campaign names and statuses, similarity score, suggested relationship type badge with advisory caption "possible relationship · operator review required", and per-dimension score breakdown. A "Dismiss" button removes the entry from the current session view only — no server write occurs.

**`ui/dashboard/src/lib/api.js`** additions: `getActors`, `getActor`, `getActorStability`, `getActorSuggestions`.

---

## 5. API Surface Added in Phase 7

### New endpoints — actors router (`/api/actors`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/actors` | Create actor profile |
| `GET` | `/api/actors` | List actor profiles |
| `GET` | `/api/actors/suggestions` | Candidate campaign pairs (read-only) |
| `GET` | `/api/actors/{id}` | Actor profile detail |
| `GET` | `/api/actors/{id}/stability` | Aggregated stability view (read-only) |
| `PATCH` | `/api/actors/{id}` | Partial update |
| `POST` | `/api/actors/{id}/campaigns` | Link a campaign to an actor (201; validates actor, campaign, rel_type; 409 on duplicate) |
| `GET` | `/api/actors/{id}/campaigns` | Campaigns linked to an actor with metadata |
| `DELETE` | `/api/actors/{id}/campaigns/{lineage_id}` | Remove a campaign-actor link (204; hard delete of lineage row only) |

### New endpoints — alerts router

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/alerts` | List behavioral drift alerts |
| `POST` | `/api/alerts/{id}/acknowledge` | Acknowledge an alert |
| `GET` | `/api/campaigns/{id}/alerts` | Alerts for a specific campaign |

### New endpoints — campaigns router (additions)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/campaigns/sparse` | Sparse campaign list |
| `GET` | `/api/campaigns/{id}/weight-profile` | Per-campaign similarity weight profile |
| `GET` | `/api/campaigns/{id}/actors` | Actors linked to this campaign |

All endpoints use the existing `require_jwt_or_api_key` dependency. No new authentication mechanism.

---

## 6. Dashboard Surface Added in Phase 7

| Component | Location | Description |
|-----------|----------|-------------|
| `ActorPanel.jsx` | After `Campaigns` panel | Actor profiles list, expandable stability detail, review candidates |

---

## 7. Data Model Changes

### New tables in Phase 7

| Table | Created by | Purpose |
|-------|-----------|---------|
| `campaign_weight_profiles` | A1 | Per-campaign similarity weight adjustments from analyst reviews |
| `behavioral_alerts` | A2 | Drift threshold crossing records requiring operator acknowledgement |

### Existing tables that gained usage

The following tables were created in Phase 6 Group D (empty schema foundations) and are now active in Phase 7:

| Table | Phase 6 state | Phase 7 state |
|-------|--------------|--------------|
| `actor_profiles` | Schema exists, no endpoints | CRUD API, suggestion engine, stability view, dashboard panel |
| `campaign_lineage` | Schema exists, no endpoints | Full HTTP API: write via `POST /api/actors/{id}/campaigns`; read via `GET /api/actors/{id}/campaigns` and `GET /api/campaigns/{id}/actors`; delete via `DELETE /api/actors/{id}/campaigns/{lineage_id}` |

### Indexes added in Phase 7

- `idx_lineage_actor ON campaign_lineage(actor_profile_id)` — migration added in B1
- `idx_lineage_campaign ON campaign_lineage(campaign_id)` — migration added in B1
- `idx_alerts_campaign ON behavioral_alerts(campaign_id)` — added in A2
- `idx_alerts_triggered ON behavioral_alerts(triggered_at)` — added in A2
- `idx_alerts_acknowledged ON behavioral_alerts(acknowledged_at)` — added in A2

---

## 8. Safety Boundaries

Phase 7 did not relax any architectural invariant established in Phases 4–6. The following boundaries held throughout:

**No automatic actor attribution.** No clustering event, lifecycle transition, AI analysis, or analytics job creates or modifies `actor_profiles` or `campaign_lineage` rows. Every write to these tables requires an explicit operator API call. The suggestion engine computes similarity scores and returns them; it does not act on them.

**No campaign merging.** Campaigns are immutable historical records. Actor identity is expressed through `campaign_lineage` as an overlay. The `campaigns` table is unchanged by actor operations.

**No AI involvement.** No Phase 7 code path calls `get_ai_backend()` or any AI layer function. Actor names are typed by the operator. Relationship types are selected from a defined vocabulary. The suggestion engine uses the same deterministic `compute_weighted_similarity()` function as the clustering algorithm.

**No federation.** No federation endpoints, no keypair generation, no received fingerprint tables, no peer configuration, no cross-deployment logic of any kind. Phase 8 boundary is intact.

**Clustering algorithm unchanged.** `app/intelligence/clustering.py` core logic is not modified. Weight profiles are consumed at the call site (before invoking `compute_weighted_similarity()`); the function itself is unchanged.

**Read-only suggestion engine.** `GET /api/actors/suggestions` and `build_actor_suggestions()` never write to any table. Tests verify this invariant explicitly.

**Drift alerts are informational.** Acknowledging an alert does not modify campaigns, fingerprints, weight profiles, or clustering decisions. No automated action follows from an alert.

---

## 9. What Remains Deliberately Excluded

The following items were in scope for Phase 7 per the blueprint but were not implemented, or were deliberately out of scope.

| Item | Reason |
|------|--------|
| Server-side suggestion dismissal | Session-only dismissal sufficient for Phase 7; blueprint §17 confirms this |
| Bulk uncertain association review | Single-observation review sufficient for Phase 7 |
| AI actor profile enrichment | AI may not participate in attribution decisions — not planned |
| Automated drift remediation | Alerting surfaces the signal; operators decide the response — not planned |
| Actor-to-actor relationship modeling | Requires actor identity to be established first — long-term |
| Federation implementation | Phase 8; operational prerequisites not yet met |
| Representative fingerprint auto-computation for actor profiles | `actor_profiles.representative_fingerprint_json` exists but is not auto-populated; reserved for operator-assigned descriptors |
| `actor_profiles.behavioral_stability_json` auto-population | Not auto-populated; the B4 endpoint computes this at request time from linked campaign data |

---

## 10. Known Limitations

**Weight profile activation.** `campaign_weight_profiles` are created only after a campaign accumulates `WEIGHT_PROFILE_MIN_REVIEWS` (default 3) analyst-reviewed observations. New deployments start with global defaults everywhere. The calibration benefit accrues over time as the analyst review queue is worked.

**BackgroundTasks process model.** Inherited from Phase 6: AI jobs run in the same OS process as the HTTP server. A server restart during a job run leaves the job in `running` state; TTL enforcement in `GET /api/jobs/{job_id}` mitigates this. Not a Phase 7 concern directly, but noted for completeness.

**SQLite write serialization.** Concurrent weight profile updates or alert insertions are serialized by SQLite WAL mode. Acceptable for single-operator deployments; high-concurrency production deployments require PostgreSQL.

**Suggestion engine O(n²) complexity.** Pairwise comparison across all eligible campaigns is O(n²). At 500 campaigns this produces up to 124,750 pairs per request. Acceptable for single-operator deployments with realistic campaign counts; a future optimization could precompute suggestions in the analytics job.

---

## 11. Validation Summary

| Check | Result |
|-------|--------|
| `pytest -q` (full test suite) | 1626 passed, 3 skipped |
| `black --check .` | Pass |
| `ruff check .` | Pass |
| `pre-commit run --all-files` | Pass |
| Frontend build (`npm run build`) | Pass (1.29s, no errors) |
| Route ordering invariant (suggestions before /{id}) | Verified |
| No write to actor_profiles/campaign_lineage from non-actor code | Verified via integration tests |
| No AI imports in actors router | Verified via invariant test |
| No federation imports in actors router | Verified via invariant test |
| B3/B4 endpoints return 200 with empty data, never write | Verified via integration tests |

---

## 12. Why Phase 7 Is Complete

Phase 7's two missions are both satisfied.

**Feedback loops are closed.** Analyst review decisions from the Phase 6 review queue now produce per-campaign weight profiles that make the clustering algorithm responsive to accumulated operator judgment. Behavioral drift signals from `fingerprint_history` and `behavioral_stability_json` now surface as alerts with configurable thresholds. Sparse campaigns are now queryable as a distinct data quality category. These were the three specific gaps identified in the Phase 6 handoff.

**Actor identity is activated.** The `actor_profiles` and `campaign_lineage` tables created empty in Phase 6 are now fully operational. Operators can create actor profiles, link campaigns to actors with an explicit relationship type, view campaign pairs that are candidates for attribution, inspect actor-level stability across linked campaigns, and acknowledge drift alerts for campaigns under attribution. The campaign-to-actor linking API (`POST/GET/DELETE /api/actors/{id}/campaigns`, `GET /api/campaigns/{id}/actors`) completes the Group B surface. The invariants from §3 of the blueprint held throughout: no attribution is automatic, no AI touches attribution decisions, no federation code exists, and the clustering algorithm is unchanged.

Phase 8 — Behavioral Federation — remains conditional on operational prerequisites (two willing deployments, validated fingerprint serialization format, key management runbook). Those prerequisites do not exist. Phase 7's local intelligence foundation is complete.

---

*Cross-references: [PHASE_7_BLUEPRINT.md](PHASE_7_BLUEPRINT.md) · [PHASE_6_CLOSEOUT.md](PHASE_6_CLOSEOUT.md) · [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md)*
