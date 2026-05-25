# LegionTrap TI — Phase 2 Blueprint: GeoIP Enrichment and Intelligence Layer

**Document type:** Implementation blueprint — Phase 2 architectural plan
**Audience:** Engineers and autonomous agents performing Phase 2 work
**Last reviewed:** 2026-05-25
**Status:** Pre-implementation. Phase 2 has not started. Read this before writing any Phase 2 code.
**Prerequisites:** Phases 0, 1A, and 1B are complete and merged to `main`.

---

## Planning Structure: Macro Layers and Implementation Units

Phase 2 is organized at two levels: a **conceptual planning layer** and a **granular implementation layer**. These must not be confused.

### Conceptual Macro Layers (planning vocabulary only)

Three capability layers structure the overall direction:

| Layer | Label | Active in Phase 2? | PR scope |
|---|---|---|---|
| **Layer 1** | **Intelligence Foundation** — enrich raw events with geo/ASN context; build per-IP scoring and tagging | Yes | PRs 1–3 |
| **Layer 2** | **Intelligence Visibility** — expose enriched data as explicit API endpoints with defined response contracts and aggregated analytics | Yes | PRs 4–5 |
| **Layer 3** | **AI Reasoning** — retrieval pipelines, structured context builders, AI orchestration, reasoning workflows, narrative analysis | **No — future work** | — |

**Layer 3 (AI Reasoning) is not part of active Phase 2 implementation.** It corresponds to Phase 5 in the existing `ROADMAP.md`. It has external dependencies (Claude API or Ollama), different data prerequisites (sufficient enriched event history for meaningful analysis), and a higher risk profile. A separate blueprint will govern that phase when Layers 1 and 2 are stable.

**Layer 2 (Intelligence Visibility) means explicit API endpoints with defined response contracts**, tested independently of any frontend. "Dashboard-facing backend structures" is not a valid Phase 2 deliverable description — every deliverable must be expressed as a named endpoint, a response schema, or a named repository method. Speculative frontend coupling has no place in this blueprint.

### Implementation Units (PR-sized sub-phases)

Macro layers are the planning vocabulary. The actual implementation must remain split into small, independently-mergeable PRs. Each PR must:

- touch a limited, defined file set
- have isolated tests with named pass/fail criteria
- have an unambiguous, verifiable exit criterion
- be mergeable and deployable independently of later PRs

Large phases produce large blast radii. An autonomous agent implementing a macro-layer in a single session has no clean recovery point if something goes wrong mid-way. Small PRs are the blast-radius control mechanism.

See [Section 21](#21-implementation-execution-order) for the recommended PR sequence.

---

## 1. Phase 2 Mission

Phase 2 transforms raw events into enriched intelligence records. Every event that arrives with a routable public IP should leave the ingest pipeline with geographic context (country, city) and organizational context (ASN). IP addresses that appear repeatedly should accumulate a computed threat classification and confidence score based purely on observed behavior.

By the end of Phase 2, an operator should be able to query `GET /api/intelligence/ips` and receive a ranked, enriched, tagged list of the IPs that have interacted with their sensors — without opening a spreadsheet.

Phase 2 does not detect campaigns, does not reason over behavioral patterns, and does not call any external API. It improves data quality at the point of ingest and makes that enriched data queryable.

---

## 2. What Phase 2 Includes

- **Phase 2A:** GeoIP and ASN enrichment wired into the ingest pipeline
- **Phase 2B:** Enrichment caching via the `source_ips` table (skip GeoIP lookup for known IPs)
- **Phase 2C:** Rule-based threat tagging and heuristic confidence scoring on `source_ips`
- **Phase 2D:** Intelligence query endpoints exposing enriched IP data
- **Phase 2E:** Schema readiness audit — verify indexes and JOIN patterns support Phase 5/6 queries

---

## 3. What Phase 2 Explicitly Excludes

| Item | Reason |
|---|---|
| External enrichment APIs (VirusTotal, Shodan, AbuseIPDB) | Network calls in the request path; privacy leakage risk |
| Machine learning | No labeled data; premature complexity |
| Campaign detection or behavioral clustering | Phase 6 concern; data insufficient until Phase 3+ events accumulate |
| Async background workers (Celery, asyncio queues) | Not needed for local file reads; Phase 5+ concern |
| Kafka or message brokers | Not needed at current scale |
| PostgreSQL migration | SQLite is authoritative and performing; no trigger for migration |
| GeoLite2-ASN.mmdb integration | Requires separate MaxMind download; defer until operator confirms availability |
| WHOIS lookups | Too slow for synchronous ingest path |
| Feed subscriptions (threat intel feeds) | Phase 4 or later |
| Modifying ingest reliability guarantees | Enrichment must fail gracefully; ingest must never be blocked by enrichment |

---

## 4. Current State: What's Already Ready

The following Phase 2 infrastructure already exists and must not be recreated:

**Schemas (`app/schemas/models.py`):**
- `EnrichedEvent(HoneypotEvent)` — has `country_code`, `country_name`, `city`, `asn`, `asn_org` fields
- All fields are nullable; failure falls back to `HoneypotEvent` with `NULL` geo fields

**Repository (`app/db/repository.py`):**
- `insert_event()` — already handles both `HoneypotEvent` and `EnrichedEvent`; checks `isinstance` and maps geo fields
- `upsert_source_ip()` — already accepts `country_code`, `country_name`, `asn`, `asn_org` params

**Database schema:**
- `events` table — already has `country_code`, `country_name`, `city`, `asn`, `asn_org` columns
- `source_ips` table — already has `country_code`, `country_name`, `asn`, `asn_org`, `reputation_score`, `tags`

**GeoIP library:**
- `geoip2` is in `requirements.txt`
- `storage/GeoLite2-City.mmdb` is present **locally** — `storage/` is gitignored; this file is never committed to the repository; it must be provisioned by each operator (see Section 5)

**What is missing:**
- `app/utils/geoip.py` does not exist yet
- The ingest pipeline produces `HoneypotEvent` (no geo fields)
- `source_ips` enrichment cache check is not implemented
- Intelligence endpoints do not exist

---

## 5. GeoIP Enrichment Approach

### Database file provisioning

```
storage/GeoLite2-City.mmdb    — country, city data (present locally; gitignored)
storage/GeoLite2-ASN.mmdb     — ASN data (not present; defer to later)
```

**These files are never committed to the repository.** `storage/` is fully gitignored. Each operator must download and place the MaxMind database files manually before enrichment will function. The application and tests must work correctly when these files are absent — degraded gracefully, not broken.

Download source: [MaxMind GeoLite2 Free Geolocation Data](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) (free account required). Place the extracted `.mmdb` file at `storage/GeoLite2-City.mmdb`. Do not commit it.

`GeoLite2-City.mmdb` does not contain ASN data. The `geoip2` City reader returns `None` for `traits.autonomous_system_number` — ASN fields require a separate `GeoLite2-ASN.mmdb` file. ASN fields remain NULL until that file is provisioned and `_asn_reader` is initialized.

Do not fail startup or ingest if either file is absent. Check for file existence at reader initialization and log a warning. Reads against a missing reader return a dict of all-`None` values.

### Module: `app/utils/geoip.py`

```python
# Module-level lazy-initialized singletons. Created on first lookup call.
_city_reader: geoip2.database.Reader | None = None
_asn_reader: geoip2.database.Reader | None = None

def enrich_ip(ip: str) -> dict[str, str | int | None]:
    """
    Return geo/ASN context for a routable public IPv4 address.
    Returns a dict with keys: country_code, country_name, city, asn, asn_org.
    All values are None on any error (file missing, IP not in DB, private IP).
    Never raises.
    """
```

The function wraps all reader calls in `try/except Exception`. Any failure returns a dict of `None` values.

Thread safety: `geoip2.database.Reader` is thread-safe for concurrent reads once initialized. Use a module-level lock only for initialization. FastAPI runs in a thread pool; concurrent ingest calls are expected.

### Where enrichment runs

Enrichment runs **synchronously** in the ingest handler, between normalization and the database write:

```
Stage 3: normalize → HoneypotEvent
Stage 3.5: enrich → EnrichedEvent  ← NEW (Phase 2A)
Stage 4: deduplication check
Stage 5: (Phase 3) — currently pass-through
Stage 6: INSERT raw_events + events + UPSERT source_ips
Stage 7: INSERT audit_log
```

Rationale: `GeoLite2-City.mmdb` is a local memory-mapped file read. The lookup is sub-millisecond. No network call, no blocking I/O. Running it synchronously avoids the complexity of a background enrichment worker and keeps enrichment latency predictable.

If the lookup returns all `None` (file missing, IP not in DB), a `HoneypotEvent` is used instead of `EnrichedEvent`. The ingest proceeds normally.

---

## 6. Source IP Caching Strategy

The `source_ips` table is the enrichment cache. Its purpose is to:
1. Avoid running a GeoIP lookup for every event from a known IP
2. Accumulate per-IP intelligence across all events (event_count, tags, score)
3. Serve as the primary data source for intelligence endpoints (not the events table)

### Cache check before lookup

Before calling `enrich_ip()`, check whether the IP is already in `source_ips` with populated geo fields:

```python
# In ingest.py, Phase 2B:
cached_geo = repo.get_source_ip_geo(event.src_ip)
if cached_geo:
    enrichment = cached_geo          # use cache, skip GeoIP read
else:
    enrichment = geoip.enrich_ip(event.src_ip)   # run lookup, populate cache
```

This reduces GeoIP lookups to one per unique IP. For a sensor receiving repeated probes from the same IP (common for SSH brute-force), the cache hit rate will be high once the source_ips table is warm.

### New repository method required: `get_source_ip_geo`

```python
def get_source_ip_geo(self, ip: str) -> dict | None:
    """
    Return cached geo fields for ip if the source_ips row exists and has
    country_code populated. Returns None if ip is unknown or geo is NULL.
    """
```

Returns `None` on cache miss. The caller then runs GeoIP and proceeds with enrichment.

### Cache write: `upsert_source_ip` update behavior

The existing `upsert_source_ip()` ON CONFLICT handler updates only `last_seen` and `event_count`. This is correct for Phase 1. For Phase 2, the upsert must also write geo fields on first insert (already implemented) and must NOT overwrite them on subsequent inserts (already implemented by not including geo in the UPDATE clause).

No change to `upsert_source_ip()` is needed for Phase 2A. The cache write is handled by the existing first-insert behavior.

---

## 7. Event Enrichment Update Strategy

### On ingest (Phase 2A)

Every event with a non-null `src_ip` goes through enrichment at ingest time:

1. Check source_ips cache → geo fields present? Use them.
2. Not cached → `enrich_ip(src_ip)` → wrap result in `EnrichedEvent`
3. `insert_event(enriched_event)` → events table gets geo fields
4. `upsert_source_ip(ip, ts, geo_fields)` → source_ips gets geo fields on first insert

### Historical events (already in DB before Phase 2)

Events in the database before Phase 2A is deployed have NULL geo fields. A backfill migration is NOT required for Phase 2. Historical events remain with NULL geo fields. New events from the same IPs will populate `source_ips` with geo data, making the IP intelligence queryable going forward.

If a future backfill is needed, it should be implemented as a standalone `scripts/backfill_geoip.py` script, not as an Alembic migration and not as application startup logic.

---

## 8. Failure Isolation Rules

These rules are non-negotiable and must be preserved across all Phase 2 changes:

| Rule | Implementation |
|---|---|
| GeoIP failure must not fail ingest | `enrich_ip()` wraps all reader calls in `try/except`; returns all-None on any error |
| Missing mmdb file must not fail startup | Check file existence at reader init; log warning; return None on lookup |
| GeoIP failure must not affect audit log write | Audit log write is already isolated in a separate session |
| Cache miss must not fail enrichment | Fall back to GeoIP lookup; fall back to NULL geo if lookup also fails |
| Intelligence endpoint failure must not affect ingest | Separate router; no shared state with ingest path |
| Tag/score computation failure must not fail ingest | Wrapped in try/except; source_ips updated best-effort |

---

## 9. Synchronous vs. Asynchronous Enrichment

**Phase 2A–2C: synchronous.**

GeoIP enrichment is a local memory-mapped file read (~0.1–0.5 ms per lookup). Running it synchronously in the ingest handler is appropriate and avoids the complexity of a background worker.

Do not introduce a background task queue for Phase 2. FastAPI's `BackgroundTasks` is a reasonable option if needed but adds complexity without benefit at current scale.

**Phase 5 and later: reconsider.**

When AI analysis runs during ingest, or when external enrichment APIs are added, a background worker becomes necessary. Phase 2 must not introduce patterns that block that transition. Keep the enrichment call cleanly isolated in Stage 3.5 so it can be extracted to a worker call in a future phase without restructuring the ingest handler.

---

## 10. Confidence and Scoring Model (Phase 2C)

**Approach: heuristic, not statistical, not ML.**

The `source_ips.reputation_score` field (REAL, 0.0–1.0) holds a computed score based on observable facts from the events table. It is updated each time an IP is seen.

### Initial scoring rules

```
score = 0.0

if event_count >= 100:        score += 0.3
elif event_count >= 10:       score += 0.1

if "brute-force" in tags:     score += 0.3
if "scanner" in tags:         score += 0.2
if "command-exec" in tags:    score += 0.3
if "malware" in tags:         score += 0.3

score = min(score, 1.0)
```

These thresholds are initial values. They will need tuning against real data. Document them in `app/utils/scoring.py` so they can be adjusted without touching the repository.

### Where scoring runs

Score computation runs as part of `upsert_source_ip()` in Phase 2C. The method receives current tags and recomputes the score. Alternatively, add a separate `update_source_ip_intelligence(ip, tags, score)` method if keeping the upsert method focused.

---

## 11. Threat Classification and Tagging (Phase 2C)

Tags are stored as a JSON array string in `source_ips.tags`. Examples: `'["brute-force", "scanner"]'`.

### Initial tag rules

| Tag | Condition |
|---|---|
| `brute-force` | Any `auth_failed` event from this IP |
| `auth-success` | Any `auth_success` event from this IP |
| `scanner` | Any `port_scan` or `http_probe` event from this IP |
| `command-exec` | Any `command_exec` event from this IP |
| `malware` | Any `malware_upload` event from this IP |

Tags are computed from the distinct `event_type` values seen for the IP. They are additive — once a tag is set, it is not removed even if later events stop matching that type.

### Where tagging runs

Tag computation requires a query over the events table: `SELECT DISTINCT event_type FROM events WHERE src_ip = :ip`. This query runs once per ingest for a known IP when tags need to be updated.

To avoid running this on every single event, only recompute tags when the event introduces a new `event_type` not already represented in the current tags. This requires passing the current tags and the new event_type into the computation function.

### Implementation location

`app/utils/scoring.py` — pure functions, no DB imports. Takes current tags (list), new event type (str), and current event count (int). Returns updated tags list and new score float.

---

## 12. Correlation and Campaign Detection Boundaries

Phase 2 does not implement campaign detection. The boundary is:

- **In scope for Phase 2:** Per-IP enrichment, tagging, scoring, intelligence queries
- **Out of scope for Phase 2:** Cross-IP correlation, behavioral fingerprinting, temporal clustering, campaign IDs

Phase 2E exists to ensure the data model is ready for Phase 5/6, not to build any correlation logic. The deliverable for 2E is a documented set of candidate queries and an index review, not new code.

No `campaign_id` values will be written in Phase 2. The `events.campaign_id` column remains NULL.

### On "basic correlation logic"

This term has appeared in Phase 2 planning discussions and is **explicitly excluded from Phase 2 scope**.

Any task described as "basic correlation logic" is disqualified unless it can be restated as one of the following concrete, single-IP-scoped operations already defined in this document:

- per-IP event type aggregation (used by the tagging engine — Section 11)
- per-IP event count accumulation (used by scoring — Section 10)
- per-IP geo/ASN lookup and caching (used by enrichment — Sections 5–7)

Cross-IP pattern matching, behavioral clustering, temporal analysis, IP grouping by shared behavior, and campaign assignment are Phase 6 work. If a proposed Phase 2 task uses the word "correlation" without a precise, single-IP-scoped implementation definition that maps to an existing section of this document, it does not belong in Phase 2.

---

## 13. Database Schema Impact

### No migrations needed for Phase 2A or 2B

All required columns already exist:
- `events`: `country_code`, `country_name`, `city`, `asn`, `asn_org`
- `source_ips`: `country_code`, `country_name`, `asn`, `asn_org`, `reputation_score`, `tags`

### Phase 2C: no new columns

`reputation_score` and `tags` are already in `source_ips`. No schema migration is needed.

### Phase 2D: no schema changes

Intelligence endpoints are read-only queries against existing tables.

### Phase 2E: potential index additions

After observing real query patterns from Phase 2D endpoints, consider:
- `source_ips(reputation_score DESC)` — for ranking endpoints
- `source_ips(tags)` — partial index for tag filtering (SQLite supports expression indexes on `json_each`)
- `events(src_ip, event_type)` — for per-IP event type aggregation used in scoring

Write new index additions as an Alembic migration: `0002_phase2_intelligence_indexes.py`.

---

## 14. Required Repository Methods

Add to `app/db/repository.py`:

### Phase 2B

```python
def get_source_ip_geo(self, ip: str) -> dict | None:
    """
    Return cached geo fields for ip if source_ips row exists and country_code
    is populated. Returns None on cache miss. Used to skip GeoIP lookup for
    known IPs.
    Keys: country_code, country_name, asn, asn_org.
    """
```

### Phase 2C

```python
def get_source_ip_event_types(self, ip: str) -> list[str]:
    """
    Return list of distinct event_type values seen from ip.
    Used for tag computation during ingest.
    """

def update_source_ip_intelligence(
    self,
    ip: str,
    tags: list[str],
    reputation_score: float,
) -> None:
    """
    Update tags and reputation_score on an existing source_ips row.
    tags is serialized as JSON. Called after scoring computation.
    """
```

### Phase 2D

```python
def list_source_ips(
    self,
    limit: int = 100,
    offset: int = 0,
    min_score: float | None = None,
    country_code: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """
    Return paginated source_ips rows with optional filters.
    Ordered by reputation_score DESC, event_count DESC.
    """

def get_source_ip(self, ip: str) -> dict | None:
    """Return a single source_ips row by IP, or None if not found."""

def get_top_asns(self, limit: int = 10) -> list[dict]:
    """Return top ASNs by event count: [{asn, asn_org, event_count, ip_count}]."""

def get_top_countries(self, limit: int = 10) -> list[dict]:
    """Return top countries by event count: [{country_code, country_name, event_count, ip_count}]."""
```

---

## 15. Required API Endpoints

### Phase 2D: `app/routers/intelligence.py`

All endpoints require `require_jwt_or_api_key`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/intelligence/ips` | Paginated enriched IP list with scores and tags. Query params: `limit`, `offset`, `min_score`, `country`, `tag` |
| `GET` | `/api/intelligence/ips/{ip}` | Single IP detail: all source_ips fields plus event type breakdown |
| `GET` | `/api/intelligence/top-asns` | Top N ASNs by event count |
| `GET` | `/api/intelligence/top-countries` | Top N countries by event count |

### Response shape for `GET /api/intelligence/ips/{ip}`

```json
{
  "ip": "1.2.3.4",
  "first_seen": "2025-10-28T18:31:08+00:00",
  "last_seen": "2026-05-25T10:00:00+00:00",
  "event_count": 847,
  "country_code": "CN",
  "country_name": "China",
  "asn": 4134,
  "asn_org": "CHINANET-BACKBONE",
  "reputation_score": 0.9,
  "tags": ["brute-force", "scanner"],
  "event_type_breakdown": {
    "auth_failed": 820,
    "port_scan": 27
  }
}
```

---

## 16. Testing Strategy

### Phase 2A tests

| Test | File | Assertion |
|---|---|---|
| `test_enrich_ip_returns_geo` | `tests/unit/test_geoip.py` | `enrich_ip("8.8.8.8")` returns non-None country_code |
| `test_enrich_ip_missing_mmdb` | `tests/unit/test_geoip.py` | Missing mmdb returns all-None without raising |
| `test_enrich_ip_private_ip` | `tests/unit/test_geoip.py` | Private IP returns all-None without raising |
| `test_ingest_populates_geo_on_events` | `tests/integration/test_enrichment.py` | POST ingest → events row has non-NULL country_code |
| `test_ingest_succeeds_without_mmdb` | `tests/integration/test_enrichment.py` | Missing mmdb → ingest still returns 200, geo fields NULL |

### Phase 2B tests

| Test | Assertion |
|---|---|
| `test_cache_hit_skips_geoip` | Second ingest of same IP does not call `enrich_ip()` |
| `test_get_source_ip_geo_returns_none_for_unknown_ip` | Unknown IP returns None |
| `test_get_source_ip_geo_returns_none_if_no_geo` | Known IP with NULL country_code returns None |

### Phase 2C tests

| Test | Assertion |
|---|---|
| `test_brute_force_tag_applied` | IP with auth_failed events has "brute-force" tag |
| `test_scanner_tag_applied` | IP with port_scan events has "scanner" tag |
| `test_reputation_score_increases_with_event_count` | score after 100 events > score after 1 event |
| `test_tags_are_additive` | Existing tags not removed when new event arrives |

### Phase 2D tests

| Test | Assertion |
|---|---|
| `test_intelligence_ips_returns_enriched_list` | Response contains score and tags fields |
| `test_intelligence_ip_detail_includes_event_breakdown` | Single IP response includes event_type_breakdown |
| `test_intelligence_ips_requires_auth` | 401 without auth header |
| `test_top_asns_returns_sorted_by_count` | First result has highest event_count |
| `test_intelligence_filter_by_tag` | `?tag=brute-force` returns only tagged IPs |

---

## 17. Operational Risks

### Risk 1: GeoLite2-City.mmdb becomes stale

MaxMind updates `GeoLite2-City.mmdb` weekly. A stale file does not fail the application but produces outdated geo data. Mitigation: document the update process in `docs/OPERATIONS.md` (not yet written); note the database date in the health endpoint response (Phase 2D addition to `/api/health`).

### Risk 2: GeoLite2-ASN.mmdb absent

ASN fields remain NULL until this file is downloaded. This is acceptable. The intelligence endpoints will show NULL ASN. Do not block Phase 2A on ASN data availability.

### Risk 3: Large `source_ips` table slowing intelligence queries

At 100k unique IPs, `list_source_ips` with reputation_score ordering requires an index on `reputation_score`. Add the index in Phase 2E after confirming the query pattern. Do not add indexes speculatively.

### Risk 4: Tag JSON parsing errors

`source_ips.tags` stores a raw JSON string. If a corruption occurs (empty string, malformed JSON), `json.loads()` raises `ValueError`. All tag reads must be wrapped in `try/except`; return an empty list on parse failure.

### Risk 5: GeoIP lookup adds latency at high ingest volume

A sub-millisecond local read at 100 events/second adds ~100ms/second of CPU time — negligible. At 10,000 events/second, reconsider. Monitor with the existing audit log event counts; if latency increases unexpectedly, profile before adding caching complexity.

---

## 18. Complexity Controls

These constraints apply to all Phase 2 implementation:

1. **No new dependencies** for Phase 2A/2B. `geoip2` is already in `requirements.txt`.
2. **No new background workers.** Enrichment runs synchronously in the ingest handler.
3. **No external network calls** in the request path, ever.
4. **No SQL in routers.** Intelligence endpoints call repository methods; zero SQL in `intelligence.py`.
5. **`app/utils/scoring.py` must have no DB imports.** Pure functions: in → out. Testable without a database.
6. **`app/utils/geoip.py` must have no FastAPI or SQLAlchemy imports.** Pure enrichment utility.
7. **Each Phase 2 sub-phase is a separate PR.** Do not bundle 2A + 2B + 2C into a single PR.
8. **130/130 tests must still pass** (or equivalent) before any Phase 2 sub-phase is merged.

---

## 19. Deferred Items

| Item | Why deferred | When to revisit |
|---|---|---|
| GeoLite2-ASN.mmdb integration | Not present; separate MaxMind download | After operator confirms file availability |
| External threat intel feeds | Network calls, privacy risk | Phase 4 |
| TOR exit node detection | Requires external list fetch | Phase 4 |
| VPN detection | No free local database | Phase 4 or later |
| Backfill of historical events with geo data | Not blocking; new events will be enriched | Only if explicitly requested |
| `is_tor_exit` and `is_vpn` columns | Schema columns exist; logic deferred | Phase 4 |
| Alert on high-score IP | Alerting is Phase 6+ | Phase 6 |
| Campaign ID assignment | campaigns table doesn't exist | Phase 6 |
| Enrichment for `dst_port`/`protocol` pattern analysis | Phase 6 behavioral analysis | Phase 6 |

---

## 20. Recommended Phase 2 Sub-Phases

### Phase 2A — GeoIP Enrichment at Ingest

**Deliverables:**
- `app/utils/geoip.py` — lazy-loaded `GeoLite2-City.mmdb` reader, `enrich_ip(ip) -> dict`
- Ingest pipeline updated: Stage 3.5 wraps `HoneypotEvent` → `EnrichedEvent`
- `events` rows now have non-NULL `country_code`/`country_name`/`city` for routable IPs
- `source_ips` rows now have non-NULL `country_code` (populated on first insert, already supported by existing `upsert_source_ip()`)
- Unit tests for `geoip.py`; integration tests for enrichment behavior
- Ingest failure isolation confirmed: missing mmdb → 200 response, NULL geo fields

**Exit criteria:** `pytest -q` passes. A real Cowrie event ingested to a fresh database produces an events row with `country_code` populated. A missing `GeoLite2-City.mmdb` does not cause any test failures.

---

### Phase 2B — Enrichment Caching via `source_ips`

**Deliverables:**
- `EventRepository.get_source_ip_geo(ip)` — reads cached geo from `source_ips`
- Ingest pipeline updated: check cache before calling `enrich_ip()`
- Unit tests for cache hit/miss behavior
- Integration test confirming `enrich_ip()` is not called on second event from same IP

**Exit criteria:** Second event from a known IP skips the GeoIP file read. Cache hit rate observable via test assertions.

---

### Phase 2C — Threat Classification and Scoring

**Deliverables:**
- `app/utils/scoring.py` — `compute_tags(current_tags, new_event_type) -> list[str]` and `compute_reputation_score(tags, event_count) -> float`
- `EventRepository.get_source_ip_event_types(ip) -> list[str]`
- `EventRepository.update_source_ip_intelligence(ip, tags, score)`
- Ingest pipeline updated: after `upsert_source_ip()`, compute and write tags + score
- Unit tests for scoring rules; integration tests for tag/score after ingest

**Exit criteria:** An IP that has sent 100+ `auth_failed` events has `tags='["brute-force"]'` and `reputation_score >= 0.4` in `source_ips`.

---

### Phase 2D — Intelligence Query Endpoints

**Deliverables:**
- `app/routers/intelligence.py` — 4 endpoints (listed in section 15)
- Repository read methods for each endpoint (listed in section 14)
- Registered in `app/main.py`
- Integration tests for each endpoint including auth check and filter behavior

**Exit criteria:** `GET /api/intelligence/ips` returns a JSON list of enriched IPs with scores and tags. `GET /api/intelligence/ips/1.2.3.4` returns a single IP detail including event type breakdown.

---

### Phase 2E — Schema Readiness Audit

**Deliverables:**
- Written audit of current indexes vs. expected Phase 5/6 query patterns (added to this document or to `DATABASE_SCHEMA.md`)
- Alembic migration `0002_phase2_intelligence_indexes.py` if any index gaps are found
- `make db-validate` passes after migration

**Exit criteria:** All known Phase 5/6 query patterns have supporting indexes. No performance surprises expected from the current schema at 1M event scale.

---

## 21. Implementation Execution Order (Recommended PR Sequence)

Each PR is a distinct, independently-mergeable unit. Complete and merge each before starting the next.

| PR | Title | Key files touched | Exit criterion |
|---|---|---|---|
| **PR 1** | GeoIP enrichment at ingest | `app/utils/geoip.py` (new), `app/routers/ingest.py`, `tests/unit/test_geoip.py` (new), `tests/integration/test_enrichment.py` (new) | `pytest -q` passes; ingest with routable IP produces non-NULL `country_code` in events row; missing mmdb produces NULL geo fields without test failure |
| **PR 2** | source_ips caching lifecycle | `app/db/repository.py` (`get_source_ip_geo`), `app/routers/ingest.py` | Second event from known IP skips GeoIP file read; confirmed by named test assertion |
| **PR 3** | Scoring and tagging engine | `app/utils/scoring.py` (new), `app/db/repository.py` (`get_source_ip_event_types`, `update_source_ip_intelligence`), `app/routers/ingest.py` | IP with 100+ `auth_failed` events has `tags='["brute-force"]'` and `reputation_score >= 0.4` in `source_ips` |
| **PR 4** | Intelligence query endpoints | `app/routers/intelligence.py` (new), `app/db/repository.py` (`list_source_ips`, `get_source_ip`), `app/main.py` | `GET /api/intelligence/ips` and `GET /api/intelligence/ips/{ip}` return correct enriched responses; 401 without auth |
| **PR 5** | Analytics aggregation endpoints | `app/routers/intelligence.py` (top-asns, top-countries routes), `app/db/repository.py` (`get_top_asns`, `get_top_countries`) | `GET /api/intelligence/top-asns` and `GET /api/intelligence/top-countries` return results sorted by event count |
| **PR 6** | Schema audit and operational cleanup | `docs/PHASE_2_BLUEPRINT.md` (update status), `docs/DATABASE_SCHEMA.md` (index audit), `alembic/versions/0002_phase2_intelligence_indexes.py` (if index gaps found) | `make db-validate` passes; Phase 5/6 query patterns documented with supporting indexes confirmed |

**Ordering rule:** PRs 1 → 2 → 3 must be merged in sequence; each depends on the previous. PRs 4 and 5 may be developed in sequence after PR 3 merges. PR 6 closes the phase and must not be started until PRs 1–5 are merged.

**No PR from this sequence may be opened until the preceding PR is merged to the feature branch.** An in-progress PR is not a merge point.

---

*Cross-references: [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) · [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) · [SECURITY_AUDIT.md](SECURITY_AUDIT.md)*
