# LegionTrap TI — Architecture

**Document type:** Technical architecture reference
**Audience:** Engineers, autonomous agents, contributors
**Last reviewed:** 2026-05-26 (Phase 5)

---

## Current Architecture Overview

LegionTrap TI is a Python FastAPI backend paired with a React frontend. Events are ingested via `POST /api/ingest`, stored in SQLite, and served from SQL queries. The frontend polls the backend every 10 seconds via authenticated HTTP requests.

### Component Map

```
Browser (React 19 + Vite)
  │
  ├── Login page
  │     └── POST /api/login → JWT token stored in localStorage
  │
  ├── Dashboard (authenticated)
  │     ├── GET /api/stats                      → KPI counters
  │     ├── GET /api/iocs/pf.conf               → Firewall block table preview
  │     ├── GET /api/events                     → Recent events table + trends chart
  │     ├── GET /api/intelligence/ips           → Top Source IPs panel
  │     ├── GET /api/intelligence/top-countries → Top Countries panel
  │     ├── GET /api/intelligence/top-asns      → Top ASNs panel
  │     ├── GET /api/campaigns                  → Campaign Intelligence panel
  │     └── POST /api/campaigns/{id}/summary    → CampaignAiPanel (operator-triggered)
  │
  └── Auto-refresh: 10–30s interval per component

FastAPI Backend (app/)
  │
  ├── app/main.py               FastAPI instance, CORS, router registration
  ├── app/routers/
  │     ├── auth_router.py      POST /api/login → JWT
  │     ├── ingest.py           POST /api/ingest (batch ingest, GeoIP enrichment, audit log)
  │     ├── stats.py            GET /api/stats
  │     ├── events.py           GET /api/events
  │     ├── iocs_pf.py          GET /api/iocs/pf.conf, /api/iocs/ufw.txt
  │     ├── intelligence.py     GET /api/intelligence/* (top IPs, countries, ASNs, IP detail)
  │     ├── exports.py          GET /api/exports/attack-navigator, /api/exports/stix
  │     ├── campaigns.py        GET /api/campaigns, /api/campaigns/{id}, /api/campaigns/{id}/observations
  │     └── analyze.py          POST /api/campaigns/{id}/summary, POST /api/campaigns/brief
  ├── app/ai/
  │     ├── __init__.py          Public API — re-exports all AI layer symbols
  │     ├── backend.py           AIBackend ABC + DisabledAIBackend, MockAIBackend,
  │     │                        OllamaAIBackend, ClaudeAIBackend, get_ai_backend()
  │     ├── prompt_builder.py    build_campaign_summary_prompt(), build_brief_prompt(),
  │     │                        format_fingerprint_summary(); SYSTEM_PROMPT, BRIEF_SYSTEM_PROMPT
  │     └── safety.py            sanitize_field(), validate_ai_output(),
  │                              contains_ip_pattern(), redact_ip_patterns()
  ├── app/intelligence/
  │     ├── fingerprint.py       build_behavioral_fingerprint() — 5-dimension feature extraction
  │     └── clustering.py        assign_or_create_campaign() — similarity clustering, reactivation detection
  ├── app/exports/
  │     ├── attack_navigator.py  Pure transform: technique counts → Navigator layer dict
  │     └── stix.py              Pure transform: IP records + campaigns → STIX 2.1 bundle dict
  ├── app/db/
  │     ├── connection.py        SQLAlchemy engine, session factory, create_all_tables()
  │     ├── repository.py        EventRepository public facade (re-exports mixin composition)
  │     └── repositories/
  │           ├── _base.py            RepositoryBase (session holder)
  │           ├── read.py             ReadRepository — event and source_ip queries
  │           ├── write.py            WriteRepository — ingest, audit_log
  │           ├── intelligence.py     IntelligenceRepository — top IPs, countries, ASNs, STIX/ATT&CK queries
  │           ├── fingerprint.py      FingerprintRepository — behavioral fingerprint upserts and lookups
  │           └── campaign.py         CampaignRepository — campaign CRUD, members, observations, export queries
  ├── app/schemas/
  │     └── models.py           RawEvent, HoneypotEvent, IngestRequest, IngestReceipt
  ├── app/utils/
  │     ├── auth.py             JWT helpers, require_jwt_or_api_key dependency
  │     └── event_utils.py      extract_src_ip(), normalize_event_type(), parse_timestamp()
  └── app/core/
        └── config.py           Pydantic Settings (env var loading)

Storage
  └── storage/
        ├── legiontrap.db        SQLite database (primary data store)
        ├── backups/             DB snapshot backups (see JSONL_RETIREMENT.md for schedule)
        └── GeoLite2-City.mmdb   IP geolocation database (active — used by ingest enrichment)

Deployment
  └── docker/
        └── docker-compose.edge.yml   Single-container edge deployment
  └── ui/backend/
        └── Dockerfile               Container image definition
```

---

## Authentication Model

The system implements a dual-credential strategy appropriate for its use case:

**API Key (`x-api-key` header):** For machine-to-machine access — pfSense cron jobs, shell scripts, CI smoke tests. The API key is compared against the `API_KEY` environment variable.

**JWT Bearer token (`Authorization: Bearer ...`):** For the React dashboard. Issued by `POST /api/login` after credential verification. Validated by `require_jwt_or_api_key` on every protected route. Token is stored in `localStorage` on the browser.

The `require_jwt_or_api_key` FastAPI dependency is the single shared authorization gate used by `stats.py`, `events.py`, and `iocs_pf.py` (`pf.conf` route). The `ufw.txt` route uses the legacy `require_api_key` dependency (API key only).

**Note:** `verify_user()` uses `pwd_context.verify()` against a bcrypt hash stored in `.env`. `DASH_PASS` must be set as a bcrypt hash; startup raises `ValueError` if unset.

---

## Event Flow (Current)

```
External honeypot (Cowrie, Dionaea, etc.)
    │
    │  POST /api/ingest  (x-api-key)
    ▼
FastAPI ingest.py
    │  Pydantic validation → normalization → deduplication
    │  GeoIP enrichment: geoip2.database.Reader → country, city, ASN
    ▼
storage/legiontrap.db (SQLite, primary store)
    │  INSERT raw_events + events + UPSERT source_ips (with geo fields)
    │  INSERT audit_log (separate session)
    │
    │  indexed SQL queries via EventRepository
    │
    ├── stats.py / events.py        → API response → Browser dashboard
    ├── iocs_pf.py                  → API response → Firewall scripts
    ├── intelligence.py             → API response → Intelligence panels
    └── exports.py + app/exports/   → API response → External TI tools
```

**Read path:** All dashboard and IOC queries run SQL against `legiontrap.db` via `EventRepository`. No file scans.

---

## Privacy Model

The privacy system operates at the IOC export layer, not at the storage layer. Events are stored with full IPs. The privacy transformation is applied on export.

**PRIVACY_MODE=off:** Full IPs exported as-is.

**PRIVACY_MODE=on, no FEED_SALT:** Last octet masked (`8.8.8.8 → 8.8.8.x`). Suitable for sharing public-facing block lists without revealing internal observations.

**PRIVACY_MODE=on, FEED_SALT set:** IP replaced with deterministic HMAC token (`8.8.8.8 → ip-a3b4c5d6e7f8`). Same IP always produces the same token for the same salt, enabling correlation without revealing the IP.

The privacy transformation is applied in `iocs_pf.py` after calling `EventRepository.get_unique_public_ips()` to retrieve IPs from SQLite.

**STIX export and PRIVACY_MODE:** The `GET /api/exports/stix` endpoint returns HTTP 422 when `PRIVACY_MODE=on`. STIX Indicator patterns require embedding raw IP addresses (`[ipv4-addr:value = '1.2.3.4']`), which is incompatible with privacy mode's intent. The ATT&CK Navigator export is unaffected because it contains no IP data.

---

## Frontend Structure

```
ui/dashboard/
  src/
    App.jsx              Root component: auth state, polling, dashboard layout
    pages/
      Login.jsx          Login form → POST /api/login → stores JWT in localStorage
    components/
      EventTrends.jsx      Recharts line chart of events over time
      RecentEvents.jsx     Tabular view of most recent events
      IntelligenceIPs.jsx  Top Source IPs table with expandable IP detail rows
      TopCountries.jsx     Top Countries panel (country, event count, unique IPs)
      TopASNs.jsx          Top ASNs panel (ASN, organization, event count, unique IPs)
      Campaigns.jsx        Campaign Intelligence panel (lifecycle badges, confidence bars, expandable detail + AI panel)
      CampaignAiPanel.jsx  Operator-triggered AI summary panel; warning always visible; never auto-generates
    lib/
      api.js               Authenticated fetch helpers (stats, events, intelligence, exports, campaigns, AI summary)
    utils/
      format.js          Date/time formatting utilities
    index.css            Global styles + dark/light mode variables
    App.css              Dashboard component styles
```

The frontend is a single-page application with no routing library. Auth state is managed in `App.jsx` via `localStorage.getItem("token")`. The 401 handler in `authFetch` clears the token and reloads the page, forcing re-login.

**Known issue:** JWT in `localStorage` is vulnerable to XSS. Future improvement: `httpOnly` cookie. See [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

---

## Known Structural Issues

**Dual app path confusion:** `ui/backend/` contains a `Dockerfile` and `requirements.txt` but no Python application code. It is a deployment stub. The actual application code lives in `app/` at the project root. These two paths should not be confused.

**Both `App.jsx` and `App.tsx` exist:** `App.jsx` is active. `App.tsx` is a stale file from a TypeScript migration attempt. It should be removed.

**Empty scaffold directory:** `ui/dashboard/app/routers/` is an empty directory — a stale scaffold from an earlier structure. It should be removed.

---

## Storage Evolution Plan

### Stage 1: SQLite — Complete

```
storage/events.jsonl  →  storage/legiontrap.db (SQLite, primary store)
```

SQLite is in production. The schema is PostgreSQL-compatible by design. Recovery is via SQLite DB snapshots; see [JSONL_RETIREMENT.md](JSONL_RETIREMENT.md) for backup and restore procedures.


### Stage 2: PostgreSQL (when required)

Migration triggers:
- Concurrent write volume exceeds SQLite's write concurrency limits
- Multi-node deployment requiring shared state
- Requirement for row-level security or multi-tenancy
- Operational requirement for managed database service (RDS, Cloud SQL)

### Stage 3: Event Streaming (long-term, if required)

For high-volume distributed deployments, an event streaming layer (Redis Streams or a lightweight message queue) between sensors and the database decouples ingestion from storage. This is only needed when ingestion volume exceeds what a single database writer can handle — not a near-term concern.

---

## AI Reasoning Architecture (Phase 5)

Phase 5 added the `app/ai/` module as a read-only reasoning layer over the existing campaign data model. The AI layer is strictly additive: removing it leaves the rest of the system fully functional.

### AI request flow

```
Operator (dashboard or API client)
    │
    │  POST /api/campaigns/{id}/summary  or  POST /api/campaigns/brief
    ▼
app/routers/analyze.py
    │  Privacy check (PRIVACY_MODE + AI_BACKEND=claude → 422)
    │  Read-only DB fetch via EventRepository (campaign, fingerprint, observations)
    │
    ▼
app/ai/prompt_builder.py
    │  Field sanitization via app/ai/safety.py
    │  Build <data> or <campaigns> XML block (source IPs never included)
    │
    ▼
app/ai/backend.py  (get_ai_backend())
    │  DisabledAIBackend → AIDisabledError → 503
    │  OllamaAIBackend   → POST http://OLLAMA_HOST/api/generate
    │  ClaudeAIBackend   → anthropic SDK → Anthropic API
    │
    ▼
app/ai/safety.py  (validate_ai_output)
    │  Reject if empty, contains IP pattern, or exceeds length limit
    │
    ▼
JSON response envelope (no DB writes at any step)
```

### AI layer isolation invariants

- The AI layer never calls `get_session()` for writes. No AI code path modifies the database.
- The ingest path (`app/routers/ingest.py`, `app/intelligence/`) has no imports from `app/ai/`.
- `app/intelligence/clustering.py` is immutable from the AI layer's perspective. AI may describe similarity scores; it cannot change them.
- `MockAIBackend` exists exclusively for test injection. It must not appear in production code paths.

### Phase 6 AI infrastructure prerequisites

1. **Async processing:** AI analysis must eventually run asynchronously to avoid blocking the API under load. A background task queue (FastAPI `BackgroundTasks` initially, Celery or asyncio worker later) is required.
2. **Output persistence:** A new `ai_outputs` table is needed before output history, audit requirements, or operator recall are implementable.
3. **AI call audit logging:** Every external AI API call should be logged to `audit_log` with timestamp and payload byte count.

See [AI_ROADMAP.md](AI_ROADMAP.md) for the broader AI integration strategy and [PHASE_5_CLOSEOUT.md](PHASE_5_CLOSEOUT.md) for the Phase 5 delivery record.

---

## Federation Architecture Direction

See [FEDERATION_VISION.md](FEDERATION_VISION.md) for the full design. Architectural requirements:

1. **Behavioral fingerprint serialization:** A standardized, privacy-safe format for representing behavioral patterns without raw IP or event content.

2. **Operator identity:** Each participating deployment has a cryptographic identity (public/private key pair) for signing contributed fingerprints.

3. **Federation transport:** HTTPS REST API for initial implementation. P2P gossip protocol for mature implementation.

4. **Received intelligence storage:** A separate table for externally received fingerprints, distinct from locally observed events.

---

## Future Infrastructure Concepts

These are directional, not commitments. They represent the infrastructure that would be required to support specific roadmap phases.

| Component | Required for | Notes |
|---|---|---|
| SQLite | Phase 1 | In use — WAL mode, FK enforcement, indexed |
| Alembic migrations | Phase 1 | In use — `alembic upgrade head` manages schema |
| Background task worker | Phase 5 (AI) | FastAPI BackgroundTasks initially |
| Redis (optional) | Phase 7 (Federation) | Session store, rate limiting, pub/sub |
| PostgreSQL | High-volume scale-out | When SQLite limits are reached |
| Reverse proxy (Caddy/nginx) | Production deployment | TLS termination, rate limiting |
| Object storage (MinIO/S3) | Long-term | PCAP storage, large artifact storage |
| Local LLM runtime (Ollama) | Phase 5 (AI) | Air-gapped deployment requirement |

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [AI_ROADMAP.md](AI_ROADMAP.md) · [SECURITY_AUDIT.md](SECURITY_AUDIT.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
