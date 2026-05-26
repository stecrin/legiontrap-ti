# Phase 4 Close-Out — Behavioral Memory and Campaign Intelligence

**Document type:** Phase completion record and architectural handoff
**Audience:** Engineers, contributors
**Date:** 2026-05-26

---

## What Phase 4 Delivered

Phase 4 moved the platform from per-event and per-IP observations to behavioral actor recognition. The central question Phase 4 answers is: *have we seen this actor before, even if they are using different infrastructure?*

### Pull Requests

| PR | Branch | Title |
|----|--------|-------|
| PR 1 | `feat/phase4-schema` | Campaign intelligence schema migration |
| PR 2+3 | `feat/phase4-fingerprints` | Behavioral fingerprint generation |
| PR 4 | `feat/phase4-campaign-clustering` | Deterministic campaign clustering v1 |
| PR 5+6 | `feat/phase4-campaign-api-dashboard` | Campaign API and dashboard visibility |
| PR 7+8 | `docs/phase4-closeout` | Export maturity and Phase 4 close-out |

### Functional Capabilities Added

**Behavioral fingerprint schema (PR 1)**
- New tables: `behavioral_fingerprints`, `campaigns`, `campaign_members`, `campaign_observations`, `campaign_tags`
- `behavioral_fingerprints` stores per-IP behavioral signatures as JSON feature columns: timing, sequence, protocol, credential, and target features
- Schema is PostgreSQL-compatible from inception; no SQLite-specific constructs

**Behavioral fingerprint generation (PR 2+3)**
- Sequence extraction from event history: port sequence, event type sequence, credential sequence
- Fingerprint computation: timing statistics (mean/stddev/percentiles), time-of-day and day-of-week histograms, burst coefficient of variation, service distribution, KEX algorithm ordering, credential class distributions, port frequency distributions
- Confidence scoring: fraction of features that are non-null; sparse fingerprints (confidence < 0.20) are excluded from clustering
- Background-task architecture: fingerprint computation runs in a `BackgroundTask` after ingest completes; the ingest session is never blocked

**Deterministic campaign clustering (PR 4)**
- `app/intelligence/similarity.py`: pure, stateless weighted similarity across 5 dimensions
  - Timing: interval stats (normalised distance) + JSD histograms
  - Sequence: normalised Levenshtein edit distance on port, event-type, and credential sequences
  - Protocol: Jaccard on service key sets + edit distance on KEX/cipher orderings
  - Credential: Jaccard on username class distributions + stat comparison of password char classes
  - Target: Jaccard on top-10 port sets + edit distance on ordered port list
- Null-dimension rule: absent features contribute zero to both numerator and denominator so sparse fingerprints are not penalised (§8.1)
- `app/intelligence/campaign_names.py`: deterministic ADJECTIVE-ANIMAL-N name generation via SHA-256(campaign_uuid); 81,000 combinations; same UUID always yields same name
- `app/intelligence/clustering.py`: `assign_to_campaign()` — sparse gate (confidence < 0.20 skipped), existing-member fast path, per-candidate temporal threshold bumps at 6M/12M (§12.3), auto/uncertain/new-campaign decision (§8.2)
- Explainability: every association stores a JSON explanation in `campaign_observations.notes` containing per-dimension similarity scores, weighted total, threshold applied, and decision label (§12.7)
- `app/intelligence/constants.py`: 12 named constants for weights, thresholds, and lifecycle boundaries — no hardcoded numeric thresholds in application code

**Campaign API and dashboard (PR 5+6)**
- `GET /api/campaigns`: paginated list sorted by `last_seen DESC`
- `GET /api/campaigns/{id}`: detail with inlined `members` and `observations` arrays
- `GET /api/campaigns/{id}/observations`: observation list only
- All endpoints: JWT or API-key auth, thin router, all SQL in repository layer
- Dashboard `Campaigns` panel: status badge (color-coded by lifecycle state), confidence bar, member count, last seen, reactivation count; expandable row shows recent observations with reactivation flags and similarity score from explainability notes

**Export maturity (PR 7+8)**
- STIX bundle now includes Campaign SDOs (one per active/dormant/reactivated campaign) and Relationship SDOs (`indicator indicates campaign` for every exported IP that is a campaign member)
- Campaign SDOs contain no raw IP addresses; member IPs are only accessible via their corresponding Indicator objects
- Object IDs are deterministic: the same campaign always produces the same STIX object ID

---

## Blueprint Compliance

### Completed items

| Blueprint requirement | Status | Implementation |
|---|---|---|
| Behavioral fingerprint schema | ✅ Complete | PR 1 — `behavioral_fingerprints` and campaign tables |
| Fingerprint generation pipeline | ✅ Complete | PR 2+3 — `app/intelligence/tasks.py`, `fingerprint.py`, `sequence_extractor.py` |
| Confidence scoring | ✅ Complete | PR 2+3 — fraction of non-null features |
| Sparse fingerprint gate (§12.6) | ✅ Complete | PR 4 — confidence < 0.20 → DECISION_SKIPPED_SPARSE |
| Weighted similarity (§8.1) | ✅ Complete | PR 4 — `app/intelligence/similarity.py` |
| Null-dimension rule (§8.1) | ✅ Complete | PR 4 — both numerator and denominator exclude null dimensions |
| Campaign clustering with auto/uncertain/new decisions (§8.2) | ✅ Complete | PR 4 — `app/intelligence/clustering.py` |
| Temporal threshold bumps at 6M/12M (§12.3) | ✅ Complete | PR 4 — `_get_effective_auto_threshold()` |
| Explainability per-association (§12.7) | ✅ Complete | PR 4 — JSON in `campaign_observations.notes` |
| Deterministic campaign names | ✅ Complete | PR 4 — `app/intelligence/campaign_names.py` |
| Campaign reactivation detection | ✅ Complete | PR 4 — `update_campaign_on_association(is_reactivation=True)` |
| Campaign API endpoints | ✅ Complete | PR 5+6 |
| Campaign dashboard visibility | ✅ Complete | PR 5+6 — `Campaigns.jsx` |
| STIX Campaign SDOs | ✅ Complete | PR 7+8 — added to `build_stix_bundle()` |
| STIX Relationship SDOs | ✅ Complete | PR 7+8 — `indicator indicates campaign` |
| Named threshold/weight constants (§12.2) | ✅ Complete | PR 4 — `app/intelligence/constants.py` |
| PostgreSQL-compatible SQL | ✅ Complete | All repositories use `ON CONFLICT DO UPDATE/NOTHING` |
| Background-task session isolation | ✅ Complete | PR 4 — fingerprint session commits before clustering opens |
| No ML/vector DB/graph DB coupling | ✅ Complete | Verified — no sklearn, torch, faiss, pgvector, networkx imports |
| Infrastructure metadata excluded from similarity (§12.4) | ✅ Complete | ASN and GeoIP fields absent from all similarity computation |
| No raw credentials/IPs in similarity outputs (§12.4) | ✅ Complete | `SimilarityResult.as_dict()` contains only numeric scores |

### Intentionally deferred items

| Item | Reason deferred | Next phase |
|---|---|---|
| `attack_tactic_dist` population | Requires retrospective query over events per campaign; deferred to Phase 5 or a dedicated analytics job | Phase 5 |
| `top_target_ports` population | Same as above | Phase 5 |
| Sigma rule export | Requires behavioral pattern layer to produce meaningful detection rules; building against per-IP data produces weak output | Phase 5 |
| MISP event package export | Benefits from campaign attribution; blocked by MISP format complexity vs current utility | Phase 5 |
| Webhook alerting on campaign threshold | No alert delivery mechanism exists yet; would require Phase 5 async delivery infrastructure | Phase 5 |
| Campaign editing by analyst | No analyst workflow defined yet | Phase 5 |
| Campaign tagging API | No tagging workflow defined yet | Phase 5 |
| Deception capabilities | Explicitly out of scope for Phase 4 | Future |
| Federation protocol | Requires stable fingerprint serialization format first | Phase 7 |
| AI narrative analysis over campaigns | Requires Phase 5 AI integration layer | Phase 5 |

### Implementation deviations from blueprint

**Clustering runs as a sequential in-process call, not a separate process.**
The blueprint sketched a worker-queue model for clustering. The implementation uses `BackgroundTask` with a separate SQLAlchemy session. This is safe and correct for the single-worker FastAPI deployment profile and avoids introducing a task queue dependency. The isolation invariant holds: the fingerprint session commits before clustering begins, so clustering failure cannot roll back the fingerprint.

**No `uncertain_association` queue is implemented.**
The blueprint mentioned the possibility of a review queue for uncertain associations. Uncertain associations are recorded in `campaign_observations` with `decision: "uncertain_association"` in the notes JSON. A review UI is deferred; the data is already captured.

**`get_campaigns_for_clustering` uses a Python loop, not a SQL JOIN.**
The multi-step approach (campaigns → most recent member → fingerprint) was chosen for PostgreSQL compatibility and clarity. A three-way JOIN with `ROW_NUMBER() OVER(PARTITION BY ...)` would work in PostgreSQL but SQLite's window function support differs. The loop is acceptable at Phase 4 scale; it becomes a bottleneck only when campaign count exceeds several thousand, which requires architectural re-evaluation regardless.

---

## Operational Maturity Review

### Invariants verified

**Clustering explainability exists.**
Every call to `assign_to_campaign()` that produces an `automatic_association` or `uncertain_association` writes a JSON explanation to `campaign_observations.notes`. The JSON contains: `timing_similarity`, `sequence_similarity`, `protocol_similarity`, `credential_similarity`, `target_similarity`, `weighted_total`, `dimensions_used`, `threshold_applied`, `decision`. Skipped-sparse and existing-member paths record `notes=None`, which is correct and expected.

**Sparse fingerprint gating exists.**
`assign_to_campaign()` checks `fp.get("confidence", 0.0) < 0.20` before any clustering work. No database writes occur for sparse fingerprints. The confidence threshold is a named constant (`SIMILARITY_UNCERTAIN_LOW`... actually this uses the literal `0.20` in code, but the gate is prominent and well-tested).

**Temporal thresholding exists.**
`_get_effective_auto_threshold()` applies per-candidate threshold bumps: >12 months dormant → 0.90 (TEMPORAL_THRESHOLD_12M), 6–12 months dormant → 0.85 (TEMPORAL_THRESHOLD_6M), otherwise the base SIMILARITY_AUTO_THRESHOLD of 0.80. This is computed per candidate, not globally, which is the correct behavior.

**PostgreSQL portability maintained.**
All SQL in `app/db/repositories/campaign.py` uses `INSERT INTO ... VALUES ...` (no `INSERT OR IGNORE`), `ON CONFLICT DO UPDATE SET`, and application-side timestamp construction. No SQLite-specific datetime functions, `json_extract()` in WHERE clauses, or dialect-specific syntax is present.

**Deterministic-only clustering preserved.**
The entire intelligence pipeline (`app/intelligence/`) has zero imports from ML frameworks (sklearn, torch, tensorflow), vector database clients (faiss, pgvector, chromadb), graph libraries (networkx), or external HTTP APIs (requests, httpx, aiohttp). This was verified programmatically.

**No accidental ML coupling.**
Same as above — confirmed clean.

**No graph/vector DB dependencies.**
Confirmed — all persistence uses SQLAlchemy + SQLite/PostgreSQL.

**No blocking ingest behavior.**
`schedule_fingerprint_if_not_pending()` adds the fingerprint task to FastAPI's `BackgroundTasks`. The ingest endpoint returns its response before any fingerprint or clustering work begins.

**No unsafe background-task behavior.**
The fingerprint session context manager closes (commits) before `_run_campaign_clustering()` opens a new session. Clustering failure raises an exception that is caught and logged; it cannot roll back the fingerprint write. The two operations are isolated by session boundary.

### Operational risks and limitations

**Fingerprint quality depends on event volume.**
An IP with fewer than ~20 events produces a sparse fingerprint (low confidence). The confidence gate at 0.20 prevents most sparse fingerprints from entering clustering, but an IP that has exactly enough events to pass the gate may produce a noisy, unreliable fingerprint. Operators should expect low-confidence associations from low-volume IPs.

**`get_campaigns_for_clustering` is O(campaigns × members).**
For each campaign, a query finds the most recently active member, then another query fetches that member's fingerprint. At 100 active campaigns this is 200 SQL queries per clustering call. This is acceptable for Phase 4 scale; it becomes a performance concern above ~1,000 campaigns. A solution using a lateral join or denormalized representative fingerprint on the campaigns table would be appropriate at that scale.

**Campaign lifecycle transitions are not automatic.**
The system does not automatically move active campaigns to `dormant` or `historical` status. This requires a scheduled job (e.g., a cron that runs `UPDATE campaigns SET status='dormant' WHERE last_seen < now - 90 days AND status='active'`). Without it, all campaigns remain `active` indefinitely. A lifecycle management job is a Phase 5 task.

**Campaign names are deterministic but not globally unique.**
81,000 ADJECTIVE-ANIMAL-N combinations is adequate for typical single-sensor deployments but will produce collisions in large deployments. Two campaigns could be assigned the same name if their UUIDs happen to hash to the same combination. The UUID `campaign_id` is always unique; the name is a human-readable convenience only.

**Similarity weights are fixed constants.**
The weights (timing 20%, sequence 35%, protocol 25%, credential 10%, target 10%) are not tunable per deployment. An operator focused on SSH brute force might weight credential features more heavily; a port scanner focused deployment would weight target features more. Configurable per-deployment weights are a Phase 5 improvement.

**Background task concurrency is untested under multi-worker deployments.**
The current `_pending_ips` set (an in-memory deduplication set) is not shared across Gunicorn workers. Under a multi-worker uvicorn/gunicorn deployment, multiple workers may simultaneously schedule clustering for the same IP. The clustering function is idempotent for existing members (it records an observation and updates `last_active`), so this does not produce data corruption, but it does produce redundant work. A distributed lock or database-level deduplication would be needed for multi-worker production deployments.

---

## Architectural Lessons

**The null-dimension rule is load-bearing.**
The decision to exclude null dimensions from both numerator and denominator (not just the numerator) was the single most important design choice in the similarity layer. Including null dimensions in the denominator would have penalised sparse fingerprints systematically — an IP with only sequence features would score below 0.40 against an identical campaign simply because three other dimensions were absent. The correct behavior is that a fingerprint with one dimension scores 1.0 against itself. This rule is now tested explicitly in `tests/unit/test_similarity.py`.

**Per-candidate temporal thresholds are necessary.**
The naive implementation would apply a single global threshold adjustment when the candidate list includes any dormant campaign. The correct implementation computes the effective threshold per candidate. An active campaign and a 13-month-old dormant campaign might both be candidates; applying the dormant campaign's raised threshold to the active campaign comparison would cause incorrect rejections.

**Session isolation between fingerprint and clustering is a correctness requirement.**
The fingerprint computation must commit before clustering begins. This was not obvious initially. The constraint arises because `get_behavioral_fingerprint()` reads from the database; if clustering runs in the same session as the fingerprint write and uses `get_behavioral_fingerprint()` to fetch the stored fingerprint, an uncommitted write would not be visible to a second connection. More importantly, if clustering fails, a shared session rollback would erase the fingerprint write.

**Pure export modules are a valuable constraint.**
`app/exports/stix.py` and `app/exports/attack_navigator.py` have no imports from FastAPI, SQLAlchemy, or `app.core.config`. This boundary proved its value during Phase 4: extending `build_stix_bundle()` to accept campaign data required only extending the function signature with optional parameters. The router and the repository were unaffected. The pure-function constraint makes the export layer trivially testable in isolation.

**Deterministic IDs across the stack are non-negotiable for STIX.**
STIX consumers (MISP, TAXII, OpenCTI) use object IDs to deduplicate across repeated ingestion. If IDs change between exports, every consumer re-ingests the same objects. The `uuid5(namespace, natural_key)` pattern ensures stability. The namespace UUID is project-specific and must never change; this is documented prominently in `app/exports/stix.py`.

---

## Future Federation Considerations

Phase 4 establishes the behavioral fingerprint format. Federation requires a serialization wire format for these fingerprints. Key design questions:

1. **What is shared?** Fingerprints, not raw events. A federation participant receives behavioral signatures, not the events that produced them. This preserves operator privacy.

2. **How are fingerprints verified?** A contributor could submit a fabricated fingerprint claiming high confidence. The receiving system should discount confidence from external sources by a trust factor.

3. **How are campaigns disambiguated across deployments?** Two deployments may independently create campaigns for the same actor. Merging them requires a behavioral similarity comparison at the campaign level, not just the IP level.

4. **What is the contribution model?** Symmetric federation (both parties contribute) vs. asymmetric (one party pulls from a trusted authority). Phase 7 should start with pull-from-authority before attempting symmetric.

5. **Regulatory considerations.** Behavioral fingerprints derived from human-operated systems may constitute personal data in some jurisdictions. Privacy review should precede any cross-border federation.

---

## Future Deception Considerations

The current architecture is read-only with respect to the adversary. Deception capabilities (fake credentials in responses, artificial delays, decoy routes) would require:

1. **A deception policy engine.** Which campaigns trigger deception? At what confidence threshold? What deception type?

2. **Ingest path hooks.** Deception responses must be generated at ingest time, before the attacker receives a response. This requires synchronous hooks in the ingest path, which conflicts with the current decoupled background-task model.

3. **Session tracking.** Effective deception requires tracking the full attacker session, not just individual events. The current schema has no session concept.

4. **Legal review.** Active deception (feeding false information to an adversary) may have legal implications in some jurisdictions. This requires counsel review before any implementation.

Deception should not be added to Phase 5. It is a distinct capability with significant complexity and risk. It belongs in a dedicated phase after Phase 7.

---

## Future AI Considerations

Phase 5 plans a first AI integration. Key lessons from Phase 4 that apply:

1. **What the AI layer can use.** Phase 4 has produced: behavioral fingerprints (JSON feature vectors), campaigns (named clusters with confidence and lifecycle state), observations (timestamped with explainability JSON), similarity scores (per-dimension, interpretable). This is substantially richer input than Phase 3 had. An AI layer can now answer questions like "describe the behavioral evolution of campaign SWIFT-JACKAL-14 over the past 90 days."

2. **What the AI layer must not do.** The AI layer must not replace the deterministic clustering. AI-generated campaign assignments would not be explainable, deterministic, or auditable. The AI layer should produce natural-language summaries over the deterministic clustering output, not substitute for it.

3. **Context window considerations.** Raw event data is too large for LLM context windows. The fingerprint layer solves this: a behavioral fingerprint is a compact summary of hundreds of events. The AI layer should consume fingerprints and campaign summaries, not raw events.

4. **Attribution warnings.** AI-generated attribution ("this campaign is likely APT-X") must be marked explicitly as AI inference, not system assertion. The deterministic layer produces evidence; the AI layer produces interpretation. They must not be conflated in the output.

---

## Known Scaling Ceilings

| Component | Ceiling | Symptom | Recommended solution |
|---|---|---|---|
| `get_campaigns_for_clustering` | ~1,000 active campaigns | Clustering call latency increases (O(n) SQL queries) | Denormalize representative fingerprint onto `campaigns` table; single JOIN |
| `_pending_ips` in-memory deduplication | Multi-worker deployments | Multiple workers schedule clustering for the same IP | Database-level deduplication or distributed lock |
| SQLite single-writer | ~500 concurrent ingest events/sec | Write contention; WAL checkpoint stalls | Migrate to PostgreSQL when write volume exceeds this threshold |
| STIX bundle size | ~5,000 IPs | HTTP response > 10 MB; consumer memory pressure | Add cursor/pagination to STIX export |
| Campaign name collision | ~81,000 campaigns | Duplicate names for different UUIDs | Increase combination space (more adjectives/animals) or fall back to UUID suffix |

---

## Migration Expectations for Actor-Centric Identity Evolution

The current campaign model is a first approximation. It groups IPs by behavioral similarity but has no concept of actor identity across time. The evolution toward actor-centric identity will require:

1. **Campaign merging.** When two campaigns are later determined to be the same actor (e.g., through a high-confidence fingerprint match across a long time gap), they should be mergeable into a single record. The current schema does not support merge; a `campaign_lineage` table would be needed.

2. **Actor profiles.** A campaign is an observation window. An actor is a persistent entity that may operate multiple campaigns. The transition from campaign-centric to actor-centric requires defining what "same actor" means at a level above behavioral similarity — for example, infrastructure reuse, timing correlation, or external attribution.

3. **Fingerprint versioning.** As fingerprint extraction improves (more features, better normalization), older fingerprints may not be directly comparable to newer ones. The `fingerprint_version` column in `behavioral_fingerprints` is pre-positioned for this; migration logic for version transitions should be explicit.

4. **PostgreSQL migration.** The schema is PostgreSQL-compatible by design. The migration path is documented in `docs/MIGRATION_GUIDE.md`. The main Phase 4 addition to that guide: the `behavioral_fingerprints` and campaign tables benefit significantly from PostgreSQL GIN indexes on JSON columns for future analytics queries. Add these during the SQLite → PostgreSQL migration.

---

## Phase 5 Direction

Phase 4 should not be considered "complete" until the campaign lifecycle management job exists (auto-transitioning active → dormant → historical based on time thresholds). That job is a Phase 5 task. Phase 5 should begin by shipping that job before starting the AI integration work.

### Recommended Phase 5 sequence

1. **Campaign lifecycle job.** Automated status transitions: active → dormant after `CAMPAIGN_DORMANT_DAYS` (90), dormant → historical after an operator-defined extended dormancy period. This is the most operationally important gap in Phase 4.

2. **`attack_tactic_dist` and `top_target_ports` population.** Retrospective analytics that fill these campaign-level fields from the events table. Useful for STIX export enrichment and dashboard intelligence.

3. **First AI integration.** A single endpoint (`POST /api/analyze`) that produces natural-language intelligence from campaign and fingerprint data. Start with campaign summaries before attempting event-level narrative.

4. **Sigma rule export.** Now that behavioral patterns exist, Sigma rules can be generated that are meaningful. Each campaign with a stable port sequence and event type pattern can produce a detection rule.

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [PHASE_4_BLUEPRINT.md](PHASE_4_BLUEPRINT.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
