# LegionTrap TI — Phase 7 Architecture Blueprint

**Document type:** Pre-implementation architecture blueprint
**Status:** Active — implementation has not begun
**Audience:** Engineers, contributors
**Date:** 2026-05-28

---

## §1 Phase 7 Mission

Phase 6 delivered longitudinal behavioral memory: fingerprint history, behavioral stability scoring, and analyst review queues for uncertain clustering associations. It collected two categories of operator intelligence that it did not consume: analyst review decisions and behavioral drift signals. Both are stored. Neither changes anything. Phase 7 closes those loops before building on them.

Phase 7 has two sequential missions:

**Mission 1 — Close the feedback loops.** Analyst review decisions accumulated in Phase 6 must become real inputs to the clustering model. Behavioral drift signals accumulated in `fingerprint_history` must surface as actionable alerts. Campaigns that have insufficient evidence must be distinguishable from campaigns that have enough. Until these three things are true, the intelligence the system accumulates does not compound — it merely accumulates.

**Mission 2 — Activate actor identity.** Phase 6 Group D created the `actor_profiles` and `campaign_lineage` tables and the `ActorRepository` with five methods. No API endpoints expose them. No UI surfaces them. Phase 7 Group B activates them: operator-facing CRUD, campaign linking, a read-only suggestion engine, and an actor-level stability view. Actor identity built on top of feedback-loop-calibrated clustering is intelligence. Actor identity built before feedback loops are closed is labeling with unearned confidence.

The sequencing is a hard constraint, not a preference. Group A must ship as a complete block before Group B begins.

---

## §2 Architectural Philosophy

### The governing principle for Phase 7

**Calibration before attribution.** The clustering algorithm currently runs with fixed global weights regardless of how many analyst reviews have been submitted. A weight profile that responds to zero reviews and a weight profile that responds to three hundred reviews are identical. That cannot be right. Phase 7 must make the accumulated operator judgment meaningful before asking operators to assign campaign-to-actor relationships on top of that judgment.

### Continuity with Phase 4, 5, and 6

Phase 4 established the deterministic clustering and behavioral fingerprint model. Phase 5 added the AI interpretation layer. Phase 6 made the AI layer accountable and extended behavioral memory longitudinally. Phase 7 must preserve every architectural invariant established in those phases.

The specific invariants that Phase 7 must never violate:
- The clustering algorithm in `app/intelligence/clustering.py` makes all campaign membership decisions. No other code path creates or modifies campaign membership.
- The AI layer is read-only with respect to campaign, fingerprint, event, and observation tables.
- The ingest path has zero imports from `app/ai/`.
- No decision in the system is made automatically without operator confirmation or initiation.

Phase 7 adds a new class of constraint: **operator judgment must be traceable.** Every weight adjustment, every actor link, every alert acknowledgement must be associated with the specific operator action that caused it. Traceability is not optional.

### Additive architecture

Phase 7 adds new tables, new repository methods, new API endpoints, and new dashboard components. It does not modify the existing clustering algorithm, similarity computation, fingerprint builder, or any Phase 4–6 intelligence pipeline. The additions are overlays and consumers of existing data, not replacements.

### Operator trust model

Phase 7 assumes a trusted operator. The system is designed for a single analyst or small team acting in good faith. Malicious review decisions — an operator deliberately confirming false associations to corrupt weight profiles — are outside the Phase 7 threat model.

This is a deliberate scope decision, not an oversight. Designing for adversarial analysts would require Byzantine-fault-tolerant consensus across multiple independent reviewers, which is both operationally inappropriate for single-operator deployments and architecturally premature.

Auditability exists for recovery, not prevention. Every weight adjustment is logged with its source observation ID, direction, and magnitude in `adjustment_log_json`. An operator who discovers a weight profile has drifted incorrectly can inspect the full log, identify which reviews drove the drift, and reconstruct how the current weights were reached. Correction is possible: the weight profile can be recomputed from scratch after removing or correcting the erroneous reviews.

Phase 7 optimizes for correctness given honest inputs, not resilience against dishonest ones.

---

## §3 Non-Negotiable Invariants

These invariants are inherited from Phases 4–6 and may not be relaxed in any Phase 7 PR under any circumstance. New Phase 7 invariants are marked **[Phase 7]**.

| Invariant | Statement |
|---|---|
| Clustering is deterministic | `app/intelligence/clustering.py` makes all campaign membership decisions using the weighted similarity algorithm. No Phase 7 code path alters this. |
| AI is read-only | No AI code path writes to campaigns, fingerprints, events, observations, actor_profiles, campaign_lineage, or campaign_weight_profiles. |
| Ingest path isolation | `app/routers/ingest.py` and `app/intelligence/` have zero imports from `app/ai/`. This must remain true after Phase 7. |
| No automatic actor attribution | **[Phase 7]** No code path writes to `actor_profiles` or `campaign_lineage` without an explicit operator API call. Clustering decisions, lifecycle transitions, AI analysis, and analytics jobs must not create or modify actor records. |
| No campaign merging | **[Phase 7]** Campaigns are immutable historical records. No Phase 7 feature merges, splits, or consolidates campaign records. Actor identity is expressed through `campaign_lineage` as an overlay, never by modifying `campaigns`. |
| Weight adjustments are explicit and traceable | **[Phase 7]** Every modification to a `campaign_weight_profiles` row must record the source observation IDs, directions, and timestamp. An operator must be able to reconstruct why current weights are what they are from the stored lineage. |
| Suggestions are read-only | **[Phase 7]** The actor suggestion engine computes and returns similarity scores. It never writes to any table. A suggestion becomes a link only when an operator calls the linking API explicitly. |
| No hidden weight changes | **[Phase 7]** The analytics job that processes reviews and updates weight profiles must not run silently without observable output. Weight profile updates must be timestamped and attributable to specific source reviews. |
| Federation is absent | **[Phase 7]** No federation endpoints, no keypair generation, no received fingerprint tables, no peer configuration, no cross-deployment logic of any kind. Federation belongs to Phase 8. |

---

## §4 What Phase 7 Is and Is Not

### Is

- Closing behavioral feedback loops by making analyst reviews affect per-campaign similarity weight profiles
- Surfacing behavioral drift as configurable, threshold-based alerts that require operator acknowledgement
- Surfacing campaigns with insufficient evidence as a distinct, queryable category
- Activating the `actor_profiles` and `campaign_lineage` tables with API endpoints and operator tooling
- Providing a read-only suggestion engine that shows campaign pairs with high fingerprint similarity
- Providing an actor-level aggregated stability view
- Providing a dashboard panel for actor profile management

### Is Not

- Modifying the clustering algorithm's core similarity computation
- Adding machine learning or learned embeddings anywhere
- Automatic actor attribution, AI-suggested actor names, or AI-initiated actor links
- Federation, peer exchange, cryptographic deployment identity, or received fingerprints
- Campaign merging, campaign splitting, or campaign consolidation
- Automated drift remediation (alerts fire; operators decide what to do)
- Removing the operator from any decision in the intelligence pipeline

---

## §5 Why Group A Must Precede Group B

The case is architectural, not organizational.

**Actor profiles built on uncalibrated clustering decisions are labels.** An operator who reviews uncertain associations for six months and has those decisions discarded builds no understanding of which behavioral dimensions are reliable for their specific attack surface. When they then link campaigns to actor profiles, those links are based on the same uncalibrated fingerprint comparisons that produced the uncertain associations in the first place. The actor profile carries false precision.

**Actor profiles built on calibrated clustering decisions are intelligence.** Once confirmed reviews adjust per-campaign weight profiles, the similarity scores used in the suggestion engine reflect the operator's actual judgment about which dimensions matter for their deployment. A suggestion with 0.87 composite similarity after weight calibration carries more meaning than a suggestion with 0.87 similarity from factory-default weights.

**The feedback loop data already exists and is waiting to be used.** Phase 6 collected analyst reviews. Not consuming them is waste. Consuming them first is correct sequencing. There is no reason to defer Group A into a later phase — it builds on existing data, requires no new sensor integration, and validates Phase 6's review collection infrastructure.

**The practical sequencing argument:** An operator running Phase 7 Group A for four weeks before Group B begins will have a calibrated weight profile for every campaign they have reviewed. When Group B ships, the suggestion engine runs against calibrated fingerprints. The suggestion quality is higher on day one of Group B than it would be if both groups shipped simultaneously.

---

## §6 Group A Architecture — Feedback Loop Closure

### §6.1 Review Decision Propagation and Weight Lineage (A1)

#### What exists in Phase 6

The `campaign_observations` table stores one row per clustering decision. Each row has:
- `notes` (TEXT): JSON blob including `{"decision": "uncertain_association", "per_dimension_scores": {...}, "weighted_total": float, ...}`
- `analyst_review_json` (TEXT): JSON blob written by `record_analyst_review()` with `{"decision": "analyst_confirmed" | "analyst_denied", "notes": str, "reviewed_at": ISO8601}`

The global similarity weights are env-var configurable constants in `app/core/config.py`:
- `WEIGHT_TIMING = 0.20`, `WEIGHT_SEQUENCE = 0.35`, `WEIGHT_PROTOCOL = 0.25`, `WEIGHT_CREDENTIAL = 0.10`, `WEIGHT_TARGET = 0.10`

No consumer reads `analyst_review_json` for any purpose after it is written.

#### What A1 adds

**New table: `campaign_weight_profiles`**

```sql
CREATE TABLE campaign_weight_profiles (
    campaign_id        TEXT PRIMARY KEY,
    weight_timing      REAL NOT NULL,
    weight_sequence    REAL NOT NULL,
    weight_protocol    REAL NOT NULL,
    weight_credential  REAL NOT NULL,
    weight_target      REAL NOT NULL,
    review_count       INTEGER NOT NULL DEFAULT 0,
    confirmed_count    INTEGER NOT NULL DEFAULT 0,
    denied_count       INTEGER NOT NULL DEFAULT 0,
    adjustment_log_json TEXT NOT NULL DEFAULT '[]',
    computed_at        TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
```

The `adjustment_log_json` column stores an append-only list of entries:
```json
[
  {
    "observation_id": "obs-uuid",
    "review_decision": "analyst_confirmed",
    "reviewed_at": "2026-05-28T...",
    "dimension_adjustments": {
      "timing": +0.02,
      "sequence": +0.03,
      "protocol": +0.01,
      "credential": 0.0,
      "target": 0.0
    },
    "weights_after": {
      "timing": 0.22,
      "sequence": 0.38,
      "protocol": 0.26,
      "credential": 0.10,
      "target": 0.10
    }
  }
]
```

#### Adjustment algorithm

The adjustment algorithm is intentionally simple. Complex adjustment logic produces weight profiles that are difficult to reason about.

**On analyst_confirmed:**
Read the `per_dimension_scores` from the original observation's `notes` JSON. For each dimension where `score > 0.70` (high-similarity dimension), apply a positive nudge of `WEIGHT_REVIEW_NUDGE` (default `0.02`). Renormalize all five weights to sum to 1.0.

**On analyst_denied:**
For each dimension where `score > 0.70` (dimensions that drove the false positive), apply a negative nudge of `WEIGHT_REVIEW_NUDGE`. Renormalize.

**Bounds:**
- No dimension weight may fall below `WEIGHT_FLOOR = 0.05`.
- No dimension weight may exceed `WEIGHT_CEILING = 0.60`.
- If a nudge would push a weight past a bound, it is clamped at the bound and the excess is not redistributed.
- Renormalization always occurs after clamping.

**Minimum review gate:**
A `campaign_weight_profiles` row is created only after a campaign has accumulated `WEIGHT_PROFILE_MIN_REVIEWS` (default `3`) analyst-reviewed observations. Below this count, the campaign uses global defaults. This prevents a single review from producing a weight profile based on one data point.

#### How the clustering algorithm consumes weight profiles

`app/intelligence/clustering.py` currently calls `compute_weighted_similarity()` with the global constants from `app/intelligence/constants.py`. Phase 7 must not modify `clustering.py`'s core logic.

The correct integration point is: when `clustering.py` calls the repo to fetch candidate campaigns (step 3 of the algorithm), each candidate can carry its weight profile. The existing `ClusteringDecision` struct and `compute_weighted_similarity()` already accept weight parameters — the calling code passes them from the environment. Phase 7 adds a lookup: before computing similarity against a campaign, check if that campaign has a `campaign_weight_profiles` row; if so, use those weights for that comparison. The per-dimension similarity scores are still returned in the explanation, now labeled with which weight set was used.

This is the only modification to the clustering call path. The algorithm is unchanged; the weight inputs may vary per campaign.

#### Auditability: weight profile endpoint

`GET /api/campaigns/{id}/weight-profile` returns:
```json
{
  "campaign_id": "...",
  "weights": {
    "timing": 0.22,
    "sequence": 0.38,
    "protocol": 0.26,
    "credential": 0.07,
    "target": 0.07
  },
  "global_defaults": {
    "timing": 0.20,
    "sequence": 0.35,
    "protocol": 0.25,
    "credential": 0.10,
    "target": 0.10
  },
  "review_count": 12,
  "confirmed_count": 9,
  "denied_count": 3,
  "adjustment_log": [...],
  "computed_at": "2026-05-28T...",
  "status": "calibrated"
}
```

When no profile exists: `"status": "using_global_defaults"`, weights equal global defaults.

#### New configuration variables

| Variable | Default | Description |
|---|---|---|
| `WEIGHT_REVIEW_NUDGE` | `0.02` | Per-dimension nudge magnitude per review |
| `WEIGHT_FLOOR` | `0.05` | Minimum value for any dimension weight |
| `WEIGHT_CEILING` | `0.60` | Maximum value for any dimension weight |
| `WEIGHT_PROFILE_MIN_REVIEWS` | `3` | Minimum reviewed observations before profile is created |
| `WEIGHT_HIGH_SCORE_GATE` | `0.70` | Similarity threshold above which a dimension is considered "high-scoring" for adjustment purposes |

---

### §6.2 Behavioral Drift Alerting (A2)

#### What exists in Phase 6

`behavioral_stability_json` on `campaigns` stores the output of `compute_campaign_stability()`, a `StabilityResult` dict with:
- `composite_score` (float 0–1)
- Per-dimension scores: `timing_stability`, `sequence_stability`, `protocol_stability`, `credential_stability`, `target_stability` (float or null)
- `status`: "ok" or "insufficient_data"
- `sample_count`, `pair_count`, `dimensions_used`, `explanation`

This data is already computed and stored by `refresh_campaign_stability()`. No alert fires when any value crosses a threshold.

#### What A2 adds

**New table: `behavioral_alerts`**

```sql
CREATE TABLE behavioral_alerts (
    id                    TEXT PRIMARY KEY,
    campaign_id           TEXT NOT NULL,
    alert_type            TEXT NOT NULL,
    dimension             TEXT,
    threshold_configured  REAL NOT NULL,
    observed_value        REAL NOT NULL,
    stability_snapshot_json TEXT NOT NULL,
    triggered_at          TEXT NOT NULL,
    acknowledged_at       TEXT,
    acknowledged_notes    TEXT,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE INDEX idx_alerts_campaign ON behavioral_alerts(campaign_id);
CREATE INDEX idx_alerts_triggered ON behavioral_alerts(triggered_at);
CREATE INDEX idx_alerts_acknowledged ON behavioral_alerts(acknowledged_at);
```

`alert_type` values: `"composite_drift"`, `"dimension_drift"`, `"rapid_change"`.

`dimension` is NULL for composite alerts, one of `timing|sequence|protocol|credential|target` for dimension alerts.

#### Alert generation job

A new function `check_campaign_drift_alerts(campaign_id)` runs as part of the existing analytics job cycle (alongside `refresh_campaign_stability()`). It reads the campaign's `behavioral_stability_json`, compares each score against the configured thresholds, and writes to `behavioral_alerts` when a threshold is crossed.

**Deduplication rule:** Before inserting a new alert, check for an existing unacknowledged alert for the same `campaign_id` and `dimension`. If one exists, do not insert. Acknowledged alerts do not block new alerts. This prevents alert storms when the analytics job runs repeatedly against a stale stability score.

**Composite alert:** fires when `composite_score < DRIFT_ALERT_COMPOSITE_THRESHOLD`.
**Dimension alerts:** fire when any per-dimension score that is not null falls below its configured threshold.

#### New configuration variables

| Variable | Default | Description |
|---|---|---|
| `DRIFT_ALERT_COMPOSITE_THRESHOLD` | `0.65` | Composite stability below which a composite_drift alert fires |
| `DRIFT_ALERT_TIMING_THRESHOLD` | `0.60` | Timing stability threshold |
| `DRIFT_ALERT_SEQUENCE_THRESHOLD` | `0.55` | Sequence stability threshold (lower default: sequence is the highest-weight dimension and is expected to be more stable) |
| `DRIFT_ALERT_PROTOCOL_THRESHOLD` | `0.60` | Protocol stability threshold |
| `DRIFT_ALERT_CREDENTIAL_THRESHOLD` | `0.55` | Credential stability threshold |
| `DRIFT_ALERT_TARGET_THRESHOLD` | `0.60` | Target stability threshold |

No alert fires for campaigns with `status = "insufficient_data"` in their stability JSON. Insufficient data is not drift.

#### API surface

- `GET /api/alerts` — list unacknowledged alerts, newest first, with optional `campaign_id` filter and `include_acknowledged=true` param
- `POST /api/alerts/{id}/acknowledge` — mark acknowledged with optional notes
- `GET /api/campaigns/{id}/alerts` — alerts for a specific campaign (acknowledged and unacknowledged)

#### Dashboard surface

Campaign cards in the existing campaign panel gain a drift alert badge when the campaign has unacknowledged alerts. Clicking the badge expands the alert detail: dimension, threshold, observed score, triggered date. Operator acknowledges from the dashboard.

---

### §6.3 Sparse Campaign Surface (A3)

#### What constitutes a sparse campaign

A campaign is sparse when it has insufficient behavioral data for the analytics pipeline to produce reliable outputs. Specifically: `behavioral_stability_json IS NULL OR representative_fingerprint_json IS NULL` AND `event_count < MIN_EVENTS_FOR_CLUSTERING`. These campaigns exist in the database but are invisible to the analytics job and produce no useful stability or suggestion outputs.

Sparse campaigns are not a lifecycle state. They are a data quality observation. The status column (`active`, `dormant`, `reactivated`, `historical`) is unchanged. Sparse is a query-time label.

#### What A3 adds

No schema changes.

**New repository method:** `list_sparse_campaigns(limit)` — queries campaigns where `representative_fingerprint_json IS NULL` AND `event_count < :min_events`, ordered by `last_seen DESC`.

**New endpoint:** `GET /api/campaigns/sparse` — returns sparse campaigns with their event_count, last_seen, and status. Distinct from `GET /api/campaigns` to avoid ambiguity.

**Dashboard:** A "sparse" label on campaign cards meeting the criteria. Operators use this to identify campaigns that may need more events before they are meaningful or that should be archived if no further activity is expected.

**No automatic action.** Sparse campaigns are not automatically archived, merged, or deleted. Surfacing them to the operator is the complete scope of A3.

---

## §7 Group B Architecture — Actor Identity

### §7.1 Relationship Type Vocabulary (B1)

The `campaign_lineage.relationship_type` column accepts any TEXT in the Phase 6 schema. Phase 7 must constrain this to a defined vocabulary before any API is built. Open strings are not accepted in the Phase 7 API.

**Defined vocabulary:**

| Type | Meaning |
|---|---|
| `primary_campaign` | This campaign is the primary or most representative campaign attributed to this actor. Used when one campaign is the clearest expression of the actor's behavior. |
| `infrastructure_reuse` | The actor reused infrastructure (ASN range, timing pattern) without matching probe sequences or credential patterns. Less definitive than primary_campaign. |
| `tactic_match` | The campaign shares attack tactics and protocol behavior with the actor's known pattern but was observed separately. |
| `temporal_overlap` | The campaign was active during the same time window as other attributed campaigns and shares a subset of behavioral dimensions. The weakest relationship type. |

The vocabulary is defined as a constant `VALID_RELATIONSHIP_TYPES: frozenset[str]` in a new module `app/intelligence/actor_constants.py`. The `link_campaign_to_actor()` method in `ActorRepository` must be updated to raise `ValueError` on an unrecognized `relationship_type`. The router validates before calling the repository method and returns HTTP 422 on invalid types.

`display_name` on actor profiles is not unique-constrained. Two separate investigations could legitimately use similar names. Uniqueness would add migration complexity with no operational benefit.

---

### §7.2 Actor Profile CRUD API (B1, continued)

New router: `app/routers/actors.py`, registered in `app/main.py` as `/api/actors`.

**`POST /api/actors`**
Request: `{display_name: str (required), notes: str (optional), confidence: float (optional, 0–1, default 0.5), status: str (optional, default "active")}`.
Calls `ActorRepository.create_actor_profile()`. Returns the created row. HTTP 201.
Operator creates this record explicitly. No clustering event triggers it.

**`GET /api/actors`**
Query params: `status` (filter), `limit` (default 50, max 200).
Calls `ActorRepository.list_actor_profiles()`. Returns list ordered by `created_at DESC`. HTTP 200.

**`GET /api/actors/{id}`**
Calls `ActorRepository.get_actor_profile()`. HTTP 200 or 404.

**`PATCH /api/actors/{id}`**
Request: partial update — any subset of `{display_name, notes, confidence, status}`.
Permitted `status` values: `"active"`, `"archived"`. No other transitions.
Updates `updated_at`. Returns updated row. HTTP 200.
No AI involvement. No automatic field population. All fields are operator-supplied.

**Authentication:** All actor endpoints use the existing `require_jwt_or_api_key` dependency. No new auth mechanism.

---

### §7.3 Campaign-to-Actor Linking API (B2)

**`POST /api/actors/{id}/campaigns`**
Request: `{campaign_id: str (required), relationship_type: str (required), confidence: float (optional, 0–1, default 0.5), evidence: str (optional)}`.
Validation order: actor exists → campaign exists → relationship_type in VALID_RELATIONSHIP_TYPES → check for duplicate (same actor_profile_id + campaign_id already exists).
Duplicate behavior: return 409 Conflict with the existing lineage_id. The operator can delete and re-create with a corrected relationship_type.
Calls `ActorRepository.link_campaign_to_actor()`. Returns created lineage row. HTTP 201.

**`GET /api/actors/{id}/campaigns`**
Returns all `campaign_lineage` rows for this actor, joined with basic campaign metadata (`status`, `last_seen`, `event_count`, `representative_fingerprint_json`). Newest first. HTTP 200.

**`DELETE /api/actors/{id}/campaigns/{lineage_id}`**
Removes a specific lineage record. Hard delete. Campaigns are unaffected. The actor profile is unaffected. The original clustering decision is unaffected.
This endpoint exists because incorrect links must be correctable. An actor profile with incorrect links has no removal path without it, and becomes a tar pit for operator trust.
HTTP 204 on success. HTTP 404 if lineage_id does not belong to actor_id.

**`GET /api/campaigns/{id}/actors`** (addition to campaigns router)
Returns `campaign_lineage` rows where `campaign_id = id`, joined with basic actor metadata. Allows operators to see which actors a campaign has been attributed to without starting from the actor view.

---

### §7.4 Actor Suggestion Engine (B3)

#### Purpose

The suggestion engine surfaces campaign pairs that are good candidates for attribution to the same actor. It is the minimum viable operator experience: without it, the actor management UI opens to a blank state and operators must manually recall which campaigns might be related.

#### Algorithm

1. Fetch all campaigns where `representative_fingerprint_json IS NOT NULL` and `status IN ('active', 'dormant', 'reactivated')`.
2. Fetch the union of campaign IDs already appearing in `campaign_lineage`. For each actor with two or more linked campaigns, pairs within that actor are excluded from suggestions.
3. For each pair of campaigns not already co-attributed, compute weighted similarity between their `representative_fingerprint_json` values using `compute_weighted_similarity()`. Use the per-campaign weight profile if present, otherwise use global defaults.
4. Return pairs where `weighted_total >= ACTOR_SUGGESTION_THRESHOLD`, sorted descending, limit `ACTOR_SUGGESTION_LIMIT`.

**`ACTOR_SUGGESTION_THRESHOLD`** defaults to `0.85`. This is intentionally higher than `SIMILARITY_AUTO_THRESHOLD` (`0.80`). Clustering auto-associates fingerprints above 0.80; actor attribution requires a more confident signal because attribution decisions are harder to reverse than campaign clustering decisions.

#### Suggested relationship type hint

For each suggestion pair, derive a hint for the most appropriate `relationship_type` based on which dimensions drove the match:
- `sequence_score >= 0.85` AND `timing_score >= 0.80` → hint `"primary_campaign"` (core tooling and tempo match)
- `timing_score >= 0.80` AND `sequence_score < 0.70` → hint `"infrastructure_reuse"` (timing pattern shared, probe sequence differs)
- `protocol_score >= 0.80` AND others lower → hint `"tactic_match"` (protocol behavior consistent)
- Default → hint `"temporal_overlap"`

The hint is a label in the API response. It is never written anywhere automatically. The operator chooses the actual relationship type when submitting the link.

#### API

**`GET /api/actors/suggestions`**
Query params: `threshold` (optional override, float), `limit` (optional, default 20, max 50).
Response:
```json
{
  "suggestions": [
    {
      "campaign_a": {"id": "...", "label": "...", "status": "...", "last_seen": "...", "event_count": 142},
      "campaign_b": {"id": "...", "label": "...", "status": "...", "last_seen": "...", "event_count": 89},
      "similarity": {
        "composite": 0.89,
        "timing": 0.91,
        "sequence": 0.87,
        "protocol": 0.85,
        "credential": 0.72,
        "target": 0.88,
        "weight_profile": "calibrated"
      },
      "suggested_relationship_type": "primary_campaign",
      "threshold_applied": 0.85
    }
  ],
  "total_campaigns_evaluated": 24,
  "total_pairs_evaluated": 276,
  "threshold": 0.85
}
```

This endpoint is read-only. It never writes to any table.

#### New configuration variables

| Variable | Default | Description |
|---|---|---|
| `ACTOR_SUGGESTION_THRESHOLD` | `0.85` | Minimum composite similarity to include in suggestions |
| `ACTOR_SUGGESTION_LIMIT` | `20` | Maximum suggestions returned per request |

---

### §7.5 Actor-Level Stability View (B4)

**`GET /api/actors/{id}/stability`**

Reads `campaign_lineage` for the actor, fetches `behavioral_stability_json` for each linked campaign, aggregates across campaigns.

Response structure:
```json
{
  "actor_id": "...",
  "actor_display_name": "...",
  "campaign_count": 4,
  "campaigns_with_stability": 3,
  "campaigns_insufficient_data": 1,
  "aggregate": {
    "composite": {"min": 0.71, "max": 0.94, "mean": 0.84},
    "timing":    {"min": 0.68, "max": 0.97, "mean": 0.83},
    "sequence":  {"min": 0.75, "max": 0.95, "mean": 0.86},
    "protocol":  {"min": 0.70, "max": 0.93, "mean": 0.81},
    "credential":{"min": 0.65, "max": 0.90, "mean": 0.77},
    "target":    {"min": 0.72, "max": 0.96, "mean": 0.85}
  },
  "campaigns": [
    {
      "campaign_id": "...",
      "relationship_type": "primary_campaign",
      "composite_score": 0.89,
      "status": "ok",
      "sample_count": 18,
      "last_computed": "..."
    }
  ],
  "computed_at": "2026-05-28T..."
}
```

This is a fully derived, read-only view. No new data is stored. Computation runs at request time over existing `behavioral_stability_json` fields. If those fields are NULL for a campaign, that campaign contributes to `campaigns_insufficient_data` but not to the aggregate.

---

### §7.6 Actor Dashboard Panel (B5)

New frontend component: `ActorPanel.jsx` (or `ActorPanel.tsx`).

Rendered in the dashboard after the existing campaign panels. The panel is off by default for operators who have created no actor profiles — it renders an empty state with guidance to create the first actor profile or review suggestions.

**Panel sections:**

1. **Actor Profiles list** — card per actor: display_name, status badge, campaign count, confidence indicator. Expandable to show linked campaigns.

2. **Linked Campaigns** (expanded actor row) — list of campaign cards within the actor, each showing: campaign label, lifecycle status, relationship_type badge, stability composite score, last_seen. Link to campaign detail.

3. **Suggestions** — separate panel section. Shows the top N suggestions from `GET /api/actors/suggestions`. Each suggestion card shows: Campaign A label, Campaign B label, composite similarity score, per-dimension mini-bars, suggested relationship type hint. Two action buttons: **Link campaigns** (opens a dialog to select/create actor profile and choose relationship type) and **Dismiss** (client-side only — removes from visible list for the current session; no server-side dismissal state in Phase 7).

4. **Drift Alerts** — a collapsible section within each actor profile showing unacknowledged drift alerts for linked campaigns.

**No automatic actions.** Every button in the actor panel requires a deliberate operator click and confirmation. The "Link campaigns" button opens a dialog; the dialog requires selecting an actor profile (or creating one) and choosing a relationship_type before submitting. There is no one-click auto-link.

**No AI involvement.** The panel does not call any AI endpoint. Actor names are typed by the operator. Relationship types are selected from a dropdown of the four defined values. Evidence notes are typed by the operator.

---

## §8 Data Model Direction

### New tables in Phase 7

| Table | Group | Purpose |
|---|---|---|
| `campaign_weight_profiles` | A1 | Per-campaign similarity weight adjustments derived from analyst reviews |
| `behavioral_alerts` | A2 | Drift threshold crossing records requiring operator acknowledgement |

### Existing tables modified in Phase 7

None. `actor_profiles` and `campaign_lineage` were created in Phase 6 Group D and are activated by API endpoints in Phase 7 Group B without schema modification.

### Indexes to add in Phase 7

For `campaign_weight_profiles`: Primary key on `campaign_id` (defined above).

For `behavioral_alerts`:
- `idx_alerts_campaign` on `campaign_id` — powers `GET /api/campaigns/{id}/alerts`
- `idx_alerts_triggered` on `triggered_at` — powers `GET /api/alerts` ordered by recency
- `idx_alerts_acknowledged` on `acknowledged_at` — powers unacknowledged filter

For `campaign_lineage` (missing from Phase 6 migration — add in first Group B migration):
- `idx_lineage_actor` on `actor_profile_id` — powers `GET /api/actors/{id}/campaigns`
- `idx_lineage_campaign` on `campaign_id` — powers `GET /api/campaigns/{id}/actors`

### Schema evolution policy

| Table | Created | Retention | Can be deleted by policy? |
|---|---|---|---|
| `campaign_weight_profiles` | Phase 7 | Permanent (intelligence asset) | No |
| `behavioral_alerts` | Phase 7 | Separate configurable (default 90d for acknowledged) | Yes (acknowledged only) |
| `actor_profiles` | Phase 6 Group D | Permanent | No |
| `campaign_lineage` | Phase 6 Group D | Permanent | No |

---

## §9 API Direction

### New routers

| File | Endpoints |
|---|---|
| `app/routers/actors.py` | `POST /api/actors`, `GET /api/actors`, `GET /api/actors/{id}`, `PATCH /api/actors/{id}`, `GET /api/actors/{id}/campaigns`, `POST /api/actors/{id}/campaigns`, `DELETE /api/actors/{id}/campaigns/{lineage_id}`, `GET /api/actors/suggestions`, `GET /api/actors/{id}/stability` |
| `app/routers/alerts.py` | `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge`, `GET /api/campaigns/{id}/alerts` |

### Additions to existing routers

| File | New endpoints |
|---|---|
| `app/routers/campaigns.py` | `GET /api/campaigns/sparse`, `GET /api/campaigns/{id}/actors`, `GET /api/campaigns/{id}/weight-profile` |

### Authentication

All new endpoints use the existing `require_jwt_or_api_key` dependency. No new authentication mechanism.

### No breaking changes

Phase 7 adds new endpoints only. No existing endpoint contract changes.

---

## §10 Auditability Requirements

| Action | What must be recorded |
|---|---|
| Weight profile update | Source observation IDs, direction (confirmed/denied), dimensions affected, magnitude, timestamp, weights before and after. Stored in `adjustment_log_json`. |
| Drift alert creation | Campaign ID, dimension, threshold configured, observed value, stability snapshot, triggered_at. |
| Alert acknowledgement | acknowledged_at timestamp, acknowledged_notes. |
| Actor profile creation | display_name, confidence, status, notes, created_at. No auto-generated fields. |
| Campaign-to-actor link | actor_profile_id, campaign_id, relationship_type, confidence, evidence, created_at. |
| Campaign-to-actor link removal | Deletion is a hard delete. Callers should record their rationale in the evidence field of the replacement link if one is created. |

An operator must be able to answer the following questions from stored data alone, without reading code:
1. Why does campaign X have the weight profile it does? → `adjustment_log_json`
2. Which analyst reviews drove the current timing weight for campaign X? → `adjustment_log_json[].observation_id` → `campaign_observations`
3. When was actor Y linked to campaign Z, and why? → `campaign_lineage.created_at`, `relationship_type`, `evidence_json`
4. What drift alert fired on campaign X, and when was it acknowledged? → `behavioral_alerts`

---

## §11 Determinism Requirements

The clustering algorithm must remain deterministic: the same inputs always produce the same output.

Phase 7 modifies which weights are used for specific per-campaign comparisons, but does not break determinism: given a fixed `campaign_weight_profiles` row and a fixed fingerprint, the similarity computation is always the same. The weight profile itself is a deterministic function of the set of analyst reviews processed.

The suggestion engine is deterministic: given fixed `representative_fingerprint_json` values and fixed weight profiles, the similarity scores and ranked suggestions are always the same.

**What does not become non-deterministic:** The clustering algorithm's decision logic, the similarity functions in `app/intelligence/similarity.py`, the fingerprint builder, the stability scorer. These are unchanged.

---

## §12 Risks and Mitigations

### False attribution

Operator links the wrong campaign to an actor. The system cannot detect this — it has no ground truth.

**Mitigations:** Deletable lineage records via `DELETE /api/actors/{id}/campaigns/{lineage_id}`. Mandatory `relationship_type` from a defined vocabulary forces the operator to characterize the nature of the relationship. Optional `evidence` field for free-text justification. `confidence` field (0–1) for operator to record their own certainty. Suggestion engine shows per-dimension scores, not just composite, so operators can see which dimensions drove the match.

### Feedback loop corruption

If operators confirm all uncertain associations without review (rubber-stamping), the weight profiles drift toward whatever the first few high-scoring dimensions were, without reflecting real behavioral signal.

**Mitigations:** `WEIGHT_PROFILE_MIN_REVIEWS = 3` prevents a single review from creating a profile. Bounded adjustments (`WEIGHT_FLOOR`, `WEIGHT_CEILING`) prevent any dimension from dominating. The weight profile endpoint (`GET /api/campaigns/{id}/weight-profile`) shows the full adjustment log, making rubber-stamping visible to an attentive operator. The adjustment magnitude (`WEIGHT_REVIEW_NUDGE = 0.02`) is small enough that many reviews are required to produce a large shift.

### Overfitting to analyst decisions

A campaign with few observations but many reviews produces a weight profile calibrated to those few observations. If the observations were atypical, the weight profile will be wrong for future comparisons.

**Mitigations:** The weight profile is a per-campaign hypothesis, not a global truth. Global default weights remain in place for all other comparisons. The `review_count` field on `campaign_weight_profiles` is returned in the weight profile endpoint, making low-review profiles explicitly identifiable.

### Weight drift

If the analytics job processes reviews repeatedly or reviews are re-processed after correction, the adjustment log grows and weights shift cumulatively.

**Mitigation:** The weight profile job must track which observation IDs have already been applied (via `adjustment_log_json`). A review that already appears in the log must not be applied again. The job is idempotent with respect to already-processed reviews.

### Actor/campaign conflation

A future implementer treats actor profiles as consolidated campaign records and begins writing event data or fingerprint data to actor tables.

**Mitigation:** The invariants in §3 are absolute. `actor_profiles` stores only: display_name, confidence, status, notes, representative_fingerprint_json (operator-set, not auto-computed), behavioral_stability_json (operator-set, not auto-computed). The `representative_fingerprint_json` and `behavioral_stability_json` fields on `actor_profiles` exist in the Phase 6 schema but must not be auto-populated in Phase 7. They are reserved for operator-assigned descriptors, not algorithm outputs.

### Suggestion engine treated as automatic attribution

If the suggestion UI presents "confirm" as the primary action and per-dimension scores are not prominent, operators may accept suggestions without reviewing the evidence.

**Mitigation:** The dashboard suggestion card must display per-dimension scores, not just composite similarity. The "Link campaigns" button opens a dialog requiring explicit actor profile selection (or creation) and explicit relationship type selection before submission. No default selection. No one-click confirm.

### Sparse campaign accumulation

Sparse campaigns accumulate in the database indefinitely without operator awareness.

**Mitigation:** A3 surfaces them. No automated archival.

---

## §13 What Must Never Happen Automatically

| Action | Why |
|---|---|
| Write to `actor_profiles` | Actor profiles are operator-created records |
| Write to `campaign_lineage` | Actor links require operator judgment |
| Merge, split, or consolidate campaigns | Campaigns are immutable historical records |
| Generate actor display names | Actor names are operator-assigned |
| Apply AI to actor linking decisions | AI may not make attribution decisions |
| Use AI output as input to suggestion engine | Suggestion engine uses only deterministic fingerprint similarity |
| Dismiss suggestions server-side | Operator dismissal in Phase 7 is session-only |
| Change VALID_RELATIONSHIP_TYPES without a new migration | The vocabulary is a data contract; changes require schema consideration |
| Process any federation, peer, or cross-deployment data | Federation is Phase 8 |

---

## §14 Anti-Complexity Rules

These rules govern the implementation choices made during Phase 7.

1. **No machine learning.** Weight adjustments use linear nudges. Suggestion engine uses the same `compute_weighted_similarity()` function as the clustering algorithm. No embeddings, no vector databases, no learned models.

2. **No gradient descent.** The weight adjustment algorithm is a bounded linear nudge with a fixed magnitude. It does not minimize a loss function.

3. **No AI involvement in any Phase 7 data flow.** From ingest to suggestion to actor linking, no code path calls the AI backend.

4. **No new background task queues.** The existing analytics job cycle is the execution context for weight profile computation and drift alert generation. No new worker infrastructure.

5. **No cross-deployment data.** Phase 7 operates entirely on locally derived fingerprints, locally stored reviews, and locally created actor profiles.

6. **Single threshold configuration.** `ACTOR_SUGGESTION_THRESHOLD` is a single scalar. Per-dimension suggestion thresholds are not configurable in Phase 7; the composite score gates suggestions.

7. **Suggestion limit is a hard cap.** `ACTOR_SUGGESTION_LIMIT = 20` prevents the suggestion engine from returning hundreds of pairs for deployments with many campaigns.

8. **No automatic alert remediation.** Drift alerts surface a signal. The operator decides what to do. No automated campaign status change, no automated suggestion surfacing, no automated weight adjustment results from an alert.

---

## §15 Exact PR Sequencing

Group A must ship as a complete, merged block before any Group B PR begins.

**Group A — Feedback Loop Closure**

| PR | Branch | Title | Key deliverables |
|----|--------|-------|-----------------|
| A1 | `feat/phase7-weight-profiles` | Review decision propagation and weight lineage | New table `campaign_weight_profiles`; migration; `WeightProfileRepository` mixin; analytics job extension; `GET /api/campaigns/{id}/weight-profile`; clustering integration point; full test coverage |
| A2 | `feat/phase7-drift-alerts` | Behavioral drift alerting | New table `behavioral_alerts`; migration; alert generation job; `AlertRepository` mixin; `app/routers/alerts.py`; dashboard alert badge; `GET /api/alerts`; `POST /api/alerts/{id}/acknowledge`; `GET /api/campaigns/{id}/alerts`; full test coverage |
| A3 | `feat/phase7-sparse-surface` | Sparse campaign surface | `list_sparse_campaigns()` repository method; `GET /api/campaigns/sparse`; dashboard sparse label; full test coverage |

No Group B PR may be opened as a draft or in review while any Group A PR is unmerged.

**Group B — Actor Identity**

| PR | Branch | Title | Key deliverables |
|----|--------|-------|-----------------|
| B1 | `feat/phase7-actor-foundation` | Relationship type vocabulary and actor CRUD API | `app/intelligence/actor_constants.py`; `VALID_RELATIONSHIP_TYPES`; `ActorRepository.link_campaign_to_actor()` validation update; `app/routers/actors.py`; `POST /api/actors`, `GET /api/actors`, `GET /api/actors/{id}`, `PATCH /api/actors/{id}`; `campaign_lineage` index migration; full test coverage |
| B2 | `feat/phase7-actor-linking` | Campaign-to-actor linking API | `POST /api/actors/{id}/campaigns`; `GET /api/actors/{id}/campaigns`; `DELETE /api/actors/{id}/campaigns/{lineage_id}`; `GET /api/campaigns/{id}/actors` (addition to campaigns router); full test coverage |
| B3 | `feat/phase7-actor-suggestions` | Actor suggestion engine | `GET /api/actors/suggestions`; pairwise similarity computation over representative fingerprints; `ACTOR_SUGGESTION_THRESHOLD` and `ACTOR_SUGGESTION_LIMIT` env vars; `suggested_relationship_type` hint derivation; full test coverage |
| B4 | `feat/phase7-actor-stability` | Actor-level stability view | `GET /api/actors/{id}/stability`; aggregation over linked campaign stability scores; full test coverage |
| B5 | `feat/phase7-actor-dashboard` | Actor dashboard panel | `ActorPanel.jsx` (or `.tsx`); actor profile list; linked campaign expansion; suggestions section; drift alert section within actor; `link_actor_to_campaign` API calls from UI; full test coverage via existing patterns |

B1 is a prerequisite for B2. B2 is a prerequisite for B3. B3 and B4 may be developed in parallel once B2 is merged. B5 requires B1–B4.

**Close-out**

| PR | Branch | Title | Key deliverables |
|----|--------|-------|-----------------|
| C1 | `docs/phase7-closeout` | Phase 7 close-out and architecture updates | `PHASE_7_CLOSEOUT.md`; `ARCHITECTURE.md` update; `ROADMAP.md` Phase 7 status update; final cross-reference check |

---

## §16 Testing Strategy

### Group A — Feedback Loop Closure

**A1 testing:**
- Test that a confirmed observation with high per-dimension scores increases those dimension weights in the profile
- Test that a denied observation with high per-dimension scores decreases those dimension weights
- Test that weights are clamped at `WEIGHT_FLOOR` and `WEIGHT_CEILING`
- Test that weights sum to 1.0 after normalization
- Test that fewer than `WEIGHT_PROFILE_MIN_REVIEWS` reviews produce no profile row
- Test that the same observation ID processed twice does not double-apply the adjustment
- Test that `GET /api/campaigns/{id}/weight-profile` returns global defaults for a campaign with no profile
- Integration test: confirm review → job run → weight profile exists → clustering uses adjusted weights for that campaign

**A2 testing:**
- Test that a stability score below threshold produces an alert record
- Test that a stability score above threshold produces no alert
- Test that `status = "insufficient_data"` produces no alert
- Test deduplication: second job run with same score does not insert duplicate unacknowledged alert
- Test that acknowledged alert does not block a new alert from firing when the score crosses threshold again
- Test `POST /api/alerts/{id}/acknowledge` updates `acknowledged_at`

**A3 testing:**
- Test that `GET /api/campaigns/sparse` returns only campaigns meeting the sparse criteria
- Test that a campaign gaining new events above `MIN_EVENTS_FOR_CLUSTERING` no longer appears

### Group B — Actor Identity

**B1 testing:**
- Test that `POST /api/actors` with missing `display_name` returns 422
- Test that `PATCH /api/actors/{id}` with an invalid `status` returns 422
- Test that `ActorRepository.link_campaign_to_actor()` with an invalid `relationship_type` raises `ValueError`
- Test all CRUD operations via the API

**B2 testing:**
- Test that `POST /api/actors/{id}/campaigns` with invalid `relationship_type` returns 422
- Test that `POST /api/actors/{id}/campaigns` with non-existent `campaign_id` returns 404
- Test that duplicate link returns 409 with existing lineage_id
- Test that `DELETE /api/actors/{id}/campaigns/{lineage_id}` with mismatched actor returns 404

**B3 testing:**
- Test that suggestion engine returns no results when no campaigns have representative fingerprints
- Test that campaigns already co-attributed to the same actor do not appear as suggestions
- Test that `threshold` override param is respected
- Test that suggestions are sorted descending by composite score
- Test that `suggested_relationship_type` hint is derived correctly from dimension scores

**B4 testing:**
- Test that campaigns with `behavioral_stability_json IS NULL` count toward `campaigns_insufficient_data`
- Test aggregate min/max/mean computations

**B5 testing:**
- UI component renders actor list when actors exist
- UI component renders empty state when no actors exist
- Suggestions section calls `GET /api/actors/suggestions`
- Link dialog does not submit without relationship_type selected

### Invariant tests (run on every PR)

- No new import from `app/ai/` in `app/routers/ingest.py` or `app/intelligence/`
- No write to `actor_profiles` or `campaign_lineage` from any non-actor-router code path
- `GET /api/actors/suggestions` returns HTTP 200 with empty list, never writes to any table

---

## §17 What is Deferred to Phase 8 or Later

| Item | Reason | Phase |
|---|---|---|
| Federation implementation | Operational prerequisites not yet met | Phase 8 |
| Ed25519 keypair generation | Federation dependency | Phase 8 |
| Received fingerprint tables | Federation dependency | Phase 8 |
| Peer configuration | Federation dependency | Phase 8 |
| Server-side suggestion dismissal | Sufficient for Phase 7 to be session-only | Phase 8 or later |
| Bulk uncertain association review | Single-observation review is sufficient for Phase 7 | Phase 8 or later |
| Actor-to-actor relationship modeling | Requires actor identity to be established first | Long-term |
| AI actor profile enrichment | AI may not participate in attribution decisions | Not planned |
| Automated drift remediation | Alerting is sufficient; remediation requires operator | Not planned |
| Representative fingerprint auto-computation for actor profiles | The `actor_profiles.representative_fingerprint_json` field exists but is not auto-populated | Phase 8+ |
| pgvector or vector embedding for suggestion engine | Linear similarity is sufficient; no measured need | Not planned |

---

## §18 Phase 6 Handoff State

The following Phase 6 deliverables are the direct inputs to Phase 7.

| Phase 6 deliverable | Phase 7 consumer |
|---|---|
| `campaign_observations.analyst_review_json` | A1 — review decision propagation |
| `campaigns.behavioral_stability_json` | A2 — drift alerting; B4 — actor stability view |
| `fingerprint_history` table | Indirectly: stability data feeds B4 via existing `behavioral_stability_json` |
| `campaigns.representative_fingerprint_json` | B3 — actor suggestion engine |
| `actor_profiles` table (empty) | B1, B2, B3, B4, B5 |
| `campaign_lineage` table (empty) | B2, B3, B4, B5 |
| `ActorRepository` (5 methods) | B1 — extended with validation; B2 — link and list methods used directly |
| `GET /api/campaigns/uncertain-associations` | Background context for A1; not modified |
| `POST /api/campaigns/uncertain-associations/{id}/review` | A1 reads the data this endpoint writes; not modified |

Phase 6 known limitations resolved by Phase 7:
- "Fingerprint history is not yet used for alerting" → resolved by A2
- "Analyst review does not propagate" → resolved by A1
- "No API endpoints for actor profiles" → resolved by B1
- "No dashboard actor UI" → resolved by B5

Phase 6 known limitations not addressed in Phase 7:
- "`BackgroundTasks` process model" → deferred; remains a Phase 8+ concern
- "`representative_fingerprint_json` and `behavioral_stability_json` require the analytics job" → unchanged; operators must still trigger the analytics job

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [PHASE_6_CLOSEOUT.md](PHASE_6_CLOSEOUT.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [BEHAVIORAL_INTELLIGENCE.md](BEHAVIORAL_INTELLIGENCE.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
