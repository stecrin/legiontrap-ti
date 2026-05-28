# LegionTrap TI — Engineering Roadmap

**Document type:** Phased development plan and architectural evolution order
**Audience:** Engineers, autonomous agents, contributors
**Last reviewed:** 2026-05-28

---

## Governing Principle

The order of this roadmap is not arbitrary. Each phase is a prerequisite for the next. Building AI reasoning before fixing storage produces a fragile system. Building federation before defining an event schema produces incompatible data. The sequence must be respected.

> **Build the foundation before building the intelligence layer. Build the intelligence layer before building the federation. Never add the next layer on an unstable base.**

---

## Current State (as of Phase 6)

| Capability | Status | Notes |
|---|---|---|
| Event storage | SQLite (WAL mode) | `storage/legiontrap.db`; JSONL replica retired (PR 4) |
| Event ingestion | `POST /api/ingest` | Batch ingest, Pydantic validation, GeoIP enrichment, deduplication |
| GeoIP enrichment | Working | `geoip2` + `GeoLite2-City.mmdb`; country, city, ASN on every routable IP |
| Stats API | Working | SQL queries via `EventRepository` |
| Intelligence API | Working | Top IPs, top countries, top ASNs, IP detail, reputation scoring |
| IOC export (pf.conf, UFW) | Working | SQL-backed; privacy masking via HMAC or octet mask |
| ATT&CK Navigator export | Working | `GET /api/exports/attack-navigator`; technique IDs from `event_types` table |
| STIX 2.1 export | Working | `GET /api/exports/stix`; Indicators + Campaign SDOs + Relationship SDOs; blocked when `PRIVACY_MODE=on` |
| JWT + API key auth | Working | bcrypt password verification; hardcoded defaults removed |
| Audit logging | Working | `audit_log` table; one row per ingest batch |
| Data retention | Working | `delete_events_before()` + `make db-prune` |
| React dashboard | Working | KPI cards, event chart, recent events, intelligence panels, campaign panel, AI summary panel, brief panel, AI output history panel |
| CI/CD | Working | Lint, test, semantic release; Black 26.5.1 pinned |
| Docker Compose | Working | Edge deployment profile |
| Behavioral fingerprinting | Working | 5-dimension behavioral fingerprint per source IP; stored in `behavioral_fingerprints` |
| Fingerprint history | Working | Append-only longitudinal snapshots in `fingerprint_history`; enables Phase 7 drift detection |
| Representative fingerprints | Working | Cluster centroid fingerprint stored per campaign in `representative_fingerprint_json` |
| Behavioral stability scoring | Working | Longitudinal stability metrics stored per campaign in `behavioral_stability_json` |
| Campaign clustering | Working | Deterministic similarity clustering; reactivation detection; `app/intelligence/clustering.py` |
| Campaign lifecycle | Working | Automatic active→dormant→historical transitions; manual trigger via `POST /api/admin/run-lifecycle-job` |
| Campaign analytics | Working | `attack_tactic_dist` and `top_target_ports` populated per campaign by analytics job |
| Configurable weights | Working | Similarity weights and lifecycle thresholds are environment variables with sane defaults |
| Campaign API | Working | `GET /api/campaigns`, `GET /api/campaigns/{id}`, `GET /api/campaigns/{id}/observations` |
| Uncertain association review | Working | `GET /api/campaigns/uncertain-associations`, `POST /api/campaigns/uncertain-associations/{id}/review` |
| AI backend abstraction | Working | `DisabledAIBackend` (default), `OllamaAIBackend`, `ClaudeAIBackend`; swapped via `AI_BACKEND` env var |
| AI safety layer | Working | Field sanitization, injection pattern detection, IP-in-output rejection, length limits |
| Async AI job infrastructure | Working | 202 Accepted contract; `processing_jobs` table; `GET /api/jobs/{job_id}` polling; TTL enforcement |
| AI output persistence | Working | Every AI artifact written to `ai_outputs` (write-once, immutable); linked to job via `ai_output_id` |
| AI audit logging | Working | Every AI API call logged to `ai_audit_log`; metadata only (no content); rate-limited requests logged |
| AI rate limiting | Working | DB-backed per-operator rate limit; `AI_MAX_REQUESTS_PER_MINUTE` env var (default: 10) |
| Campaign AI summary | Working | `POST /api/campaigns/{id}/summary`; 202 Accepted; operator-triggered; persisted to `ai_outputs` |
| Multi-campaign brief | Working | `POST /api/campaigns/brief`; 202 Accepted; optional time-window filter; persisted to `ai_outputs` |
| Campaign AI output history | Working | `GET /api/campaigns/{id}/ai-outputs`; newest-first; `CampaignAiOutputHistory` dashboard panel |
| Dashboard AI brief panel | Working | `CampaignBriefPanel` — time-window inputs, async polling, plain text, warning always visible |
| Actor identity foundations | Schema only | `actor_profiles` + `campaign_lineage` tables; `ActorRepository`; no attribution logic yet |

---

## What Must NOT Happen Too Early

These are the failure modes of premature feature expansion. Each item below, if built before its prerequisite, creates technical debt that must be torn out later.

- **AI reasoning before queryable storage.** Running LLM analysis over a flat file that is read in full on each request will not scale past a few thousand events and cannot support the query patterns that AI reasoning requires.
- **Federation before event schema.** Sharing behavioral fingerprints across deployments requires that events have a consistent, defined structure. Sharing untyped dicts is not federation; it is noise exchange.
- **MITRE ATT&CK mapping before event types.** Mapping requires a defined taxonomy of event types. Mapping undefined events produces undefined results.
- **Multi-sensor support before single-sensor reliability.** Ingestion reliability, schema validation, and error handling must be solid for one source before adding the complexity of multiple sources.
- **Commercial features before community trust.** A community that trusts the platform is the prerequisite for any commercial tier. Pursuing revenue before establishing trust poisons the well.

---

## Phase 0 — Security and Infrastructure Hygiene — **Complete**

**Goal:** Remove disqualifying issues that prevent adoption by serious operators.

These are not features. They are preconditions. No serious operator will deploy a system with plaintext password comparison, wildcard CORS, and hardcoded default secrets.

| Task | File | Priority |
|---|---|---|
| Implement bcrypt password verification in `verify_user()` | `app/utils/auth.py` | Critical |
| Restrict CORS to specific origin (configurable, default localhost) | `app/main.py` | Critical |
| Remove all hardcoded default credentials from code | `app/core/config.py`, `app/utils/auth.py` | Critical |
| Add `tmp_events_test.jsonl`, `tmp.log` to `.gitignore` | `.gitignore` | High |
| Fix `make run` entry point (stale `ui.backend.app.main:app`) | `Makefile` | Medium |
| Fix `datetime.utcnow()` deprecation in `stats.py` | `app/routers/stats.py` | Medium |
| Add rate limiting to `/api/login` | `app/routers/auth_router.py` | High |
| Cover remaining test gaps (`events.py` 31%, `auth.py` 48%) | `tests/` | High |

**Exit criteria:** `black --check`, `ruff check`, `pytest -q` all pass clean. No hardcoded credentials. No plaintext password comparison. No wildcard CORS.

---

## Phase 1 — Storage Foundation — **Complete**

**Goal:** Replace flat-file storage with a queryable database. Every downstream feature depends on this.

This is the single most important architectural decision in the project's history. The choice made here determines the ceiling for every future feature.

**Decision: SQLite → PostgreSQL migration path**
- Start with SQLite: zero infrastructure, file-based, instant setup, full SQL
- Design the schema to be PostgreSQL-compatible from day one
- Migrate to PostgreSQL when multi-user, high-volume, or concurrent write requirements emerge

| Task | Notes |
|---|---|
| Define `HoneypotEvent` Pydantic schema | Mandatory fields: `id`, `ts`, `src_ip`, `event_type`. Optional: `dst_port`, `service`, `country`, `asn`, `raw` |
| Create SQLite database with events table | Mirror the Pydantic schema |
| Migrate event reads from JSONL scan to SQL queries | All three routers: `stats.py`, `events.py`, `iocs_pf.py` |
| Maintain JSONL ingestion path during transition | Backward compatibility until ingestion API exists |
| Add database migration tooling (Alembic) | Required before schema changes accumulate |

**Exit criteria:** All API endpoints read from SQLite. JSONL file can still be used to seed the database. Query times are sub-second for up to 1 million events.

---

## Phase 2 — Ingestion API — **Complete**

**Goal:** The system must accept events over HTTP, not only via file write.

Without this, LegionTrap cannot receive events from remote sensors, cloud functions, or distributed deployments. The system remains a file reader.

| Task | Notes |
|---|---|
| `POST /api/ingest` endpoint | Accepts single event or batch; validates against `HoneypotEvent` schema |
| API key authentication for ingestion | Reuse existing `require_api_key` dependency |
| Input validation and sanitization | Reject events missing mandatory fields; log but continue on optional field errors |
| Idempotency key | Prevent duplicate events from sensor retries |
| Return structured ingest receipt | `{"accepted": N, "rejected": M, "errors": [...]}` |

**Exit criteria:** A Cowrie honeypot can POST events to LegionTrap via HTTP. Events appear in the database and the dashboard within the next polling cycle.

---

## Phase 3 — GeoIP Enrichment and Event Context — **Complete**

**Goal:** Wire in the already-installed GeoIP library. Every event gets country, city, and ASN context at ingestion time. Expose intelligence endpoints and standard exports.

| Task | Status | Notes |
|---|---|---|
| Enrich `src_ip` with country, city, ASN on ingestion | ✅ | `geoip2` + `GeoLite2-City.mmdb`; fires on every routable IP |
| Add enrichment fields to `HoneypotEvent` schema | ✅ | `country_code`, `country_name`, `city`, `asn`, `asn_org` |
| Add geographic filtering to stats endpoint | ✅ | `GET /api/intelligence/top-countries`, `GET /api/intelligence/top-asns` |
| Update dashboard to display geographic context | ✅ | IntelligenceIPs, TopCountries, TopASNs panels |
| Intelligence API — top IPs with reputation scoring | ✅ | `GET /api/intelligence/ips`, `GET /api/intelligence/ips/{ip}` |
| JSONL replica write removed from ingest path | ✅ | PR 4; `scripts/import_jsonl.py` retained for one-time migrations |
| ATT&CK Navigator export | ✅ | `GET /api/exports/attack-navigator`; technique weights from event counts |
| STIX 2.1 Indicator bundle export | ✅ | `GET /api/exports/stix`; deterministic IDs; blocked by `PRIVACY_MODE` |

**Deferred out of Phase 3:** Sigma rules, MISP event packages, campaign clustering, AI reasoning. See Phase 4 and Phase 5.

**Exit criteria met:** Every ingested event with a routable IP has country and ASN attached. The dashboard shows geographic and intelligence breakdowns. Standard TI exports are operational.

---

## Phase 4 — Campaign Intelligence and Export Maturity — **Complete**

**Duration:** 3–5 weeks
**Goal:** Move from individual event intelligence to behavioral campaign recognition. Mature the export layer with additional standard formats.

Phase 3 delivered the foundation: enriched events, a queryable intelligence layer, ATT&CK mapping, and initial STIX/Navigator exports. Phase 4 builds the first layer of memory — grouping events into campaigns and producing richer export artifacts from those clusters.

| Task | Notes |
|---|---|
| Campaign detection (simple clustering) | Group events by source ASN, port sequence, timing, tool signatures |
| `source_ips` behavioral tagging improvements | Automated tag assignment from event type patterns |
| `GET /api/campaigns` | Active and historical campaign clusters |
| Campaign recurrence detection | Alert when a known fingerprint reappears with new infrastructure |
| `GET /api/exports/stix` — Relationship objects | Add `relationship` SDOs between IPv4-Addr and Indicator once campaigns exist |
| `GET /api/exports/sigma` | Sigma rule per observed behavioral pattern |
| `GET /api/exports/misp` | MISP-compatible event package |
| STIX AttackPattern and Campaign objects | Requires campaign data; deferred from Phase 3 deliberately |
| Webhook alerting | Notify operator when campaign threshold is crossed |

**Prerequisite note:** STIX Campaign and Relationship objects, Sigma rules, and MISP packages all require campaign-level data. Do not attempt them before campaign clustering is operational.

**Exit criteria:** The system detects that a campaign observed today shares behavioral characteristics with a previously observed campaign. An analyst can export a STIX bundle containing Relationship objects. A Sigma rule can be exported for any observed behavioral pattern.

**Delivered:** Behavioral fingerprinting (5 dimensions), deterministic campaign clustering, reactivation detection, lifecycle management (active/dormant/reactivated/historical), campaign API endpoints, campaign dashboard panel, STIX Campaign + Relationship SDOs. **Deferred to Phase 5:** Sigma rules, MISP packages, webhook alerting. See [PHASE_4_CLOSEOUT.md](PHASE_4_CLOSEOUT.md) for full delivery record.

---

## Phase 5 — First AI Integration — **Complete**

**Duration:** 2–4 weeks
**Goal:** Prove the AI reasoning concept with a minimal viable implementation. Operator-triggered natural-language intelligence from real campaign data.

| Task | Notes |
|---|---|
| Campaign lifecycle maintenance | Automatic status transitions; manual trigger endpoint |
| Campaign analytics population | `attack_tactic_dist` and `top_target_ports` per campaign |
| Configurable similarity weights | Environment-variable weights and thresholds |
| AI backend abstraction | Claude, Ollama, and disabled backends behind a uniform interface |
| Prompt builder and safety layer | Field sanitization, injection detection, IP-in-output rejection |
| `POST /api/campaigns/{id}/summary` | Operator-triggered single campaign AI summary |
| Dashboard AI summary panel | `CampaignAiPanel` — never auto-generates; warning always visible |
| `POST /api/campaigns/brief` | Operator-triggered multi-campaign threat brief |

**Delivered:** AI-assisted natural-language campaign summaries and threat briefs. Every AI output is traceable to specific deterministic records. AI is additive — the system functions fully without it. See [PHASE_5_CLOSEOUT.md](PHASE_5_CLOSEOUT.md) for full delivery record, safety boundaries, known limitations, and deferred items.

---

## Phase 6 — Behavioral Memory and Campaign Intelligence — **Complete**

**Duration:** ~2 weeks (Phase 5 infrastructure build-out + Phase 6 delivery)
**Goal:** Make AI-generated intelligence accountable, auditable, and recallable. Deepen behavioral memory into a longitudinal model. Prepare actor identity foundations for Phase 7.

Phase 6 delivered in four groups. Group A shipped the async job infrastructure and AI persistence layer before any AI feature expansion. Groups B and C built on that foundation. Group D created empty schema foundations for Phase 7 without implementing attribution.

| Group | PRs | Title |
|-------|-----|-------|
| A | #51–#53 | Async job infrastructure, AI output persistence, audit logging, rate limiting |
| B | #54–#56 | Fingerprint history, representative fingerprints, behavioral stability scoring, uncertain association review queue |
| C | #57–#58 | Time-window campaign briefs, dashboard brief panel, AI output history panel |
| D | D1+D2 | Actor identity schema foundations, Phase 6 close-out documentation |

**Exit criteria met:** The system persists, audits, and serves every AI-generated artifact. Behavioral fingerprints are recorded longitudinally. Clustering decisions with uncertain confidence are surfaced to analysts for review. Actor identity tables are in place for Phase 7 assignment.

**Delivered:** See [PHASE_6_CLOSEOUT.md](PHASE_6_CLOSEOUT.md) for the complete delivery record, architectural changes, known limitations, and Phase 7 recommended direction.

---

## Phase 7 — Actor Identity and Behavioral Federation

**Duration:** 6–10 weeks
**Goal:** Build on Phase 6 actor identity foundations to enable campaign-to-actor assignment, then enable consenting operators to share behavioral fingerprints without exposing raw telemetry.

Phase 6 Group D created the `actor_profiles` and `campaign_lineage` tables and repository layer. Phase 7 activates them with API endpoints, operator tooling, and a federation protocol.

See [FEDERATION_VISION.md](FEDERATION_VISION.md) for detailed federation design. See [PHASE_6_CLOSEOUT.md](PHASE_6_CLOSEOUT.md) §10 for the recommended Phase 7 direction.

| Task | Track | Notes |
|------|-------|-------|
| Actor profile CRUD API | 1 | `POST /api/actors`, `GET /api/actors/{id}`, `PATCH /api/actors/{id}` |
| Campaign-to-actor linking API | 1 | `POST /api/actors/{id}/campaigns`, `GET /api/actors/{id}/campaigns` |
| Actor profile dashboard panel | 1 | Read-only; no automatic attribution |
| Behavioral fingerprint serialization format | 2 | Standardized, privacy-safe representation; no raw IPs |
| Operator identity management | 2 | Cryptographic keypair per deployment for signing |
| Federation push/pull API | 2 | `POST /api/federation/contribute`, `GET /api/federation/fingerprints` |
| Received intelligence integration | 2 | Imported fingerprints enrich local campaign detection |

**Exit criteria:** An operator can assign campaigns to actor profiles via API. Two independent LegionTrap deployments can exchange behavioral fingerprints. Each deployment's campaign detection improves measurably from the shared data.

---

## Long-Term Roadmap (18+ months)

These items are valid strategic directions but must not be attempted before the Phase 0–6 foundation is solid.

- **Autonomous alerting:** Webhook, Telegram, and email notifications on campaign detection events
- **Multi-agent AI analysis:** Specialized AI agents for enrichment, correlation, and report generation operating as a pipeline
- **Conversational analyst interface:** Natural language Q&A over the operator's behavioral event database
- **Autonomous incident report generation:** Structured incident reports from campaign cluster analysis
- **Commercial tier:** Managed deployment, enterprise support, enhanced AI features
- **Offensive telemetry monitoring:** Detect when your own systems are being used in attacks against others

---

## Architecture Evolution Summary

```
Phase 0:  Fix security hygiene (no architecture change)
Phase 1:  JSONL → SQLite (storage layer replacement)
Phase 2:  File ingestion → HTTP ingestion API (input layer addition)
Phase 3:  Raw events → enriched events + intelligence API + standard exports (processing + output layer)
Phase 4:  Events → campaign clusters + export maturity (memory layer foundation)
Phase 5:  Data → AI-reasoned intelligence (reasoning layer addition)
Phase 6:  Events → behavioral memory + campaigns (memory layer maturation)
Phase 7:  Local memory → federated collective intelligence (network layer addition)
```

Each arrow represents a step that builds on the previous. No step can be safely skipped.

---

*Cross-references: [ARCHITECTURE.md](ARCHITECTURE.md) · [AI_ROADMAP.md](AI_ROADMAP.md) · [SECURITY_AUDIT.md](SECURITY_AUDIT.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
