# LegionTrap TI — Engineering Roadmap

**Document type:** Phased development plan and architectural evolution order
**Audience:** Engineers, autonomous agents, contributors
**Last reviewed:** 2026-05-25

---

## Governing Principle

The order of this roadmap is not arbitrary. Each phase is a prerequisite for the next. Building AI reasoning before fixing storage produces a fragile system. Building federation before defining an event schema produces incompatible data. The sequence must be respected.

> **Build the foundation before building the intelligence layer. Build the intelligence layer before building the federation. Never add the next layer on an unstable base.**

---

## Current State (as of Phase 4)

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
| React dashboard | Working | KPI cards, event chart, recent events, intelligence panels + campaign panel |
| CI/CD | Working | Lint, test, semantic release; Black 26.5.1 pinned |
| Docker Compose | Working | Edge deployment profile |
| Behavioral fingerprinting | Working | 5-dimension behavioral fingerprint per source IP; stored in `behavioral_fingerprints` |
| Campaign clustering | Working | Deterministic similarity clustering; reactivation detection; `app/intelligence/clustering.py` |
| Campaign API | Working | `GET /api/campaigns`, `GET /api/campaigns/{id}`, `GET /api/campaigns/{id}/observations` |
| AI integration | None | Planned Phase 5 |

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

## Phase 5 — First AI Integration

**Duration:** 2–4 weeks
**Goal:** Prove the AI reasoning concept with a minimal viable implementation. A single endpoint that produces natural-language intelligence from real event data.

This is the proof-of-concept that validates the entire strategic direction. It must be built on the Phase 1–3 foundation (queryable storage, enriched events) to be meaningful.

| Task | Notes |
|---|---|
| `POST /api/analyze` | Takes a time window or event set; returns narrative threat brief |
| Claude API integration | Use structured prompting over enriched event data |
| Campaign detection (simple clustering) | Group events by source ASN, timing, port sequence |
| Natural-language brief generation | "In the last 24 hours, 3 actors probed SSH from ASN 12345..." |
| Local LLM option | Ollama integration for air-gapped deployments |

**Exit criteria:** An operator can submit a time window and receive a plain-language description of observed attack patterns. The brief is accurate and useful, not generic.

---

## Phase 6 — Behavioral Memory and Campaign Tracking

**Duration:** 4–6 weeks
**Goal:** Persistent behavioral fingerprinting that enables campaign recognition across time.

This is the strategic core of the platform. Events are not isolated incidents; they are data points in persistent behavioral patterns.

| Task | Notes |
|---|---|
| Behavioral fingerprint schema | Encode port sequences, timing distributions, User-Agent patterns, tool signatures |
| Campaign cluster model | Group events into campaigns based on behavioral similarity |
| Actor persistence table | Track campaigns across multiple observation periods |
| `GET /api/campaigns` | Return active and historical campaign clusters |
| Campaign recurrence detection | Alert when a known campaign fingerprint reappears |
| Threat scoring | Score actors by frequency, behavioral diversity, targeting patterns |

**Exit criteria:** The system identifies that a campaign observed today shares behavioral characteristics with a campaign observed three months ago, even if the IP infrastructure is entirely different.

---

## Phase 7 — Privacy-Preserving Federation

**Duration:** 6–10 weeks
**Goal:** Enable consenting operators to share behavioral fingerprints without exposing raw telemetry.

See [FEDERATION_VISION.md](FEDERATION_VISION.md) for detailed design.

| Task | Notes |
|---|---|
| Behavioral fingerprint serialization format | Standardized, privacy-safe representation of behavioral patterns |
| Federation protocol design | Push/pull model; signed submissions; operator identity management |
| Opt-in contribution mechanism | Operators explicitly choose what to share |
| Received intelligence integration | Imported fingerprints enrich local campaign detection |
| Federation API endpoints | `POST /api/federation/contribute`, `GET /api/federation/fingerprints` |

**Exit criteria:** Two independent LegionTrap deployments can exchange behavioral fingerprints. Each deployment's campaign detection improves measurably from the shared data.

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
