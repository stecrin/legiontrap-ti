# Phase 3 Close-Out — GeoIP Enrichment and Intelligence Exports

**Document type:** Phase completion record and architectural handoff
**Audience:** Engineers, contributors
**Date:** 2026-05-25

---

## What Phase 3 Delivered

Phase 3 exceeded its original scope. It was specified as a GeoIP enrichment phase; it shipped a complete intelligence layer and standard TI export capability.

### Pull Requests

| PR | Branch | Title |
|----|--------|-------|
| PR 1 | `feat/phase3-geoip-enrichment` | GeoIP enrichment on ingestion |
| PR 2 | `feat/phase3-intelligence-api` | Intelligence API (top IPs, countries, ASNs, reputation) |
| PR 3 | `feat/phase3-source-ip-reputation` | Source IP reputation scoring |
| PR 4 | `refactor/remove-jsonl-replica` | Remove JSONL replica write from ingest path |
| PR 5 | `feat/phase3-dashboard-intelligence` | Dashboard intelligence visibility panels |
| PR 6 | `feat/phase3-exports` | ATT&CK Navigator and STIX 2.1 export endpoints |

### Functional Capabilities Added

**GeoIP enrichment**
- Every ingested event with a routable source IP is enriched at ingest time with `country_code`, `country_name`, `city`, `asn`, and `asn_org`.
- Enrichment uses `geoip2.database.Reader` against the bundled `GeoLite2-City.mmdb`.
- Private, loopback, and reserved IPs are not enriched; `src_ip` is stored as NULL.

**Intelligence API (`GET /api/intelligence/*`)**
- `GET /api/intelligence/ips` — paginated list of source IPs ordered by reputation score
- `GET /api/intelligence/ips/{ip}` — full detail record for a single observed IP
- `GET /api/intelligence/top-countries` — top countries by event count with unique IP counts
- `GET /api/intelligence/top-asns` — top ASNs by event count with unique IP counts

**Reputation scoring**
- Heuristic reputation score (0.0–1.0) assigned to each `source_ips` row.
- Score computed from event count, event type diversity, and presence of high-severity event types (brute force, command execution, auth success on honeypot).

**Dashboard panels**
- IntelligenceIPs: top source IPs table with expandable detail rows showing full IP intelligence record.
- TopCountries: country breakdown with flag, event count, unique IP count.
- TopASNs: ASN breakdown with organization name, event count, unique IP count.

**ATT&CK Navigator export (`GET /api/exports/attack-navigator`)**
- Returns a full ATT&CK Navigator layer JSON.
- Technique IDs and tactic mappings come exclusively from the `event_types` table; no technique IDs are hardcoded in application code.
- Gradient `maxValue` scales dynamically to the highest observed event count.
- PRIVACY_MODE does not affect this endpoint (no IP data is exported).

**STIX 2.1 export (`GET /api/exports/stix`)**
- Returns a STIX 2.1 Bundle containing one `ipv4-addr` SCO and one `indicator` SDO per qualifying IP.
- Deterministic IDs: `uuid5` over a project namespace ensures the same IP always produces the same object IDs across exports.
- Object IDs are stable; re-exporting after new events does not invalidate previously distributed bundles.
- Blocked with HTTP 422 when `PRIVACY_MODE=on` (STIX patterns require raw IPs).
- No `stix2` library dependency — plain Python dicts.

**JSONL replica retirement (PR 4)**
- The JSONL replica write path (`tmp_events.jsonl`) was removed from the ingest route.
- `scripts/import_jsonl.py` is retained for one-time historical data migrations.
- See [JSONL_RETIREMENT.md](JSONL_RETIREMENT.md) for backup and restore procedures.

---

## Architectural Changes

### New Modules

| Module | Role |
|--------|------|
| `app/routers/intelligence.py` | Intelligence API router |
| `app/routers/exports.py` | Standard exports router |
| `app/exports/attack_navigator.py` | Pure transform: technique counts → Navigator layer |
| `app/exports/stix.py` | Pure transform: IP records → STIX 2.1 bundle |
| `app/db/repositories/intelligence.py` | SQL queries for intelligence and export data |

### Export Layer Design Rule

`app/exports/` modules are pure transformation functions. They receive plain Python dicts from the repository layer and return plain Python dicts. They have no imports from FastAPI, SQLAlchemy, or `app.core.config`. This boundary must be maintained: the export layer does not know about HTTP, database sessions, or environment configuration.

### Repository Mixin Pattern

`EventRepository` inherits from three mixin classes: `WriteRepository`, `ReadRepository`, and `IntelligenceRepository`. New query methods belong in the mixin that matches their concern. The class hierarchy is:

```
EventRepository(WriteRepository, ReadRepository, IntelligenceRepository)
```

---

## Intentional Deferrals

These items were considered during Phase 3 and explicitly deferred. They must not be added until their prerequisite layer is stable.

| Item | Reason deferred | Prerequisite |
|------|----------------|--------------|
| STIX Relationship objects | Relationships require campaign-level data to be meaningful | Campaign clustering (Phase 4) |
| STIX Campaign and AttackPattern objects | Same as above | Phase 4 |
| Sigma rule export | Sigma rules encode behavioral patterns; no behavioral pattern layer exists yet | Phase 4 |
| MISP event package export | MISP packages benefit from campaign attribution | Phase 4 |
| AI narrative analysis | No reasoning layer exists; querying raw events without semantic compression produces noise | Phase 5 |
| Campaign clustering | Requires behavioral fingerprint schema design; out of scope for Phase 3 | Phase 4 |
| Webhook alerting | No campaign detection threshold to trigger alerts against | Phase 4 |

---

## Operational Risks

**GeoLite2-City.mmdb is not auto-updated.** The bundled MaxMind database is a point-in-time snapshot. ASN and country assignments for IPs change over time. Operators should establish a process to refresh this file periodically (MaxMind provides a free update subscription).

**Reputation scoring is heuristic only.** The current reputation score is a local heuristic based on observed event patterns. It has no external feed backing. An IP with a score of 0.9 has been observed behaving maliciously against this sensor — it has not been cross-referenced with any external threat intelligence source.

**STIX bundle has no `spec_version` at the bundle level.** This is correct per the STIX 2.1 specification but differs from STIX 2.0 behavior. Consumers targeting STIX 2.0 will behave unexpectedly.

**STIX IDs are deployment-stable, not globally unique.** Two independent LegionTrap deployments observing the same IP will produce the same STIX object IDs. This is intentional (enables deduplication in MISP/TAXII) but means consumers must not assume IDs are globally allocated.

**Dashboard panels poll independently.** IntelligenceIPs, TopCountries, and TopASNs each poll on their own 30-second interval. Under heavy load this produces multiple concurrent API calls. A shared polling coordinator is a future improvement.

---

## Phase 4 Direction

Phase 4 should not start until this close-out PR is merged. The Phase 4 objective is campaign intelligence: moving from per-event and per-IP observations to behavioral campaign recognition.

### Guiding constraint

Do not build STIX Relationship objects, Sigma rules, or MISP packages until there is campaign data to populate them. Building these export formats against per-IP data produces technically correct but semantically weak output.

### Recommended Phase 4 sequence

1. **Define behavioral fingerprint schema.** What fields constitute a behavioral signature? Port sequence, timing distribution, event type sequence, tool signature (User-Agent patterns, payload fingerprints). Decide which fields are stored in `source_ips`, which require a new `behavioral_fingerprints` table.

2. **Campaign clustering.** Group `source_ips` rows into campaigns using behavioral similarity. Start simple: shared ASN + overlapping port sequences + overlapping time windows. A campaign is a set of source IPs that appear to operate as a coordinated unit.

3. **`GET /api/campaigns` endpoint.** Return active and historical campaign clusters. Each campaign has a stable ID, a behavioral summary, member IPs, first/last activity, and a confidence score.

4. **Campaign recurrence detection.** When a new IP is ingested, check whether its behavioral fingerprint matches any historical campaign. If so, flag it as a recurrence. This is the core value proposition of LegionTrap's intelligence layer.

5. **STIX Relationship and Campaign objects.** Once campaign data exists, add `relationship` SDOs (Indicator `indicates` Campaign) and `campaign` SDOs to the STIX bundle. These are the objects that make a STIX bundle actionable in a MISP or TAXII workflow.

6. **Export maturity.** Sigma rules and MISP packages naturally follow from campaign data. Defer until step 5 is complete.

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [JSONL_RETIREMENT.md](JSONL_RETIREMENT.md)*
