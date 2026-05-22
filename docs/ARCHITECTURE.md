# LegionTrap TI — Architecture

**Document type:** Technical architecture reference
**Audience:** Engineers, autonomous agents, contributors
**Last reviewed:** 2026-05-22

---

## Current Architecture Overview

LegionTrap TI is a Python FastAPI backend paired with a React frontend. Events are stored in a JSONL flat file. The backend reads that file on each request to compute statistics and generate IOC exports. The frontend polls the backend every 10 seconds via authenticated HTTP requests.

### Component Map

```
Browser (React 19 + Vite)
  │
  ├── Login page
  │     └── POST /api/login → JWT token stored in localStorage
  │
  ├── Dashboard (authenticated)
  │     ├── GET /api/stats          → KPI counters
  │     ├── GET /api/iocs/pf.conf   → Firewall block table preview
  │     ├── GET /api/events         → Recent events table
  │     └── GET /api/events         → Event trends chart
  │
  └── Auto-refresh: 10s interval

FastAPI Backend (app/)
  │
  ├── app/main.py               FastAPI instance, CORS, router registration
  ├── app/routers/
  │     ├── auth_router.py      POST /api/login → JWT
  │     ├── stats.py            GET /api/stats
  │     ├── events.py           GET /api/events
  │     └── iocs_pf.py          GET /api/iocs/pf.conf, /api/iocs/ufw.txt
  ├── app/utils/
  │     └── auth.py             JWT helpers, require_jwt_or_api_key dependency
  └── app/core/
        └── config.py           Pydantic Settings (env var loading)

Storage
  └── storage/
        ├── events.jsonl         Append-only event log (primary data store)
        ├── GeoLite2-City.mmdb   IP geolocation database (installed, unused in routes)
        └── test-events.jsonl    Test fixture (pointed to by conftest.py)

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

**Known weakness:** `verify_user()` compares the password against a plaintext `.env` value rather than a bcrypt hash. See [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

---

## Event Flow (Current)

```
External honeypot (Cowrie, Dionaea, etc.)
    │
    │  appends JSON line
    ▼
storage/events.jsonl
    │
    │  full file read on every API request
    ▼
FastAPI (stats.py / events.py / iocs_pf.py)
    │
    │  in-memory aggregation
    ▼
API response → Browser / Script / Firewall
```

**Current constraint:** The entire file is read and parsed on every API call. There is no indexing, no caching, and no persistent aggregation state. This is acceptable at low event volumes and becomes a performance problem above approximately 50,000–100,000 events.

---

## Privacy Model

The privacy system operates at the IOC export layer, not at the storage layer. Events are stored with full IPs. The privacy transformation is applied on export.

**PRIVACY_MODE=off:** Full IPs exported as-is.

**PRIVACY_MODE=on, no FEED_SALT:** Last octet masked (`8.8.8.8 → 8.8.8.x`). Suitable for sharing public-facing block lists without revealing internal observations.

**PRIVACY_MODE=on, FEED_SALT set:** IP replaced with deterministic HMAC token (`8.8.8.8 → ip-a3b4c5d6e7f8`). Same IP always produces the same token for the same salt, enabling correlation without revealing the IP.

The privacy transformation is implemented in `iocs_pf.py:_unique_public_ips_from_events()`.

---

## Frontend Structure

```
ui/dashboard/
  src/
    App.jsx              Root component: auth state, polling, dashboard layout
    pages/
      Login.jsx          Login form → POST /api/login → stores JWT in localStorage
    components/
      EventTrends.jsx    Recharts line chart of events over time
      RecentEvents.jsx   Tabular view of most recent events
    lib/
      api.js             Authenticated fetch helpers (getStats, getPfConf)
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

**Stale entry point in Makefile:** `make run` uses `ui.backend.app.main:app`, which does not exist. The correct entry point is `app.main:app`. Use `make ui` or invoke uvicorn directly.

**Both `App.jsx` and `App.tsx` exist:** `App.jsx` is active. `App.tsx` is a stale file from a TypeScript migration attempt. It should be removed.

**Empty scaffold directory:** `ui/dashboard/app/routers/` is an empty directory — a stale scaffold from an earlier structure. It should be removed.

---

## Storage Evolution Plan

The JSONL flat file must be replaced with a queryable database. The planned migration path:

### Stage 1: SQLite (current → near-term)

```
storage/events.jsonl  →  storage/legiontrap.db (SQLite)
```

SQLite provides:
- Full SQL query capability (aggregation, filtering, indexing)
- Zero additional infrastructure
- Single-file backup
- Concurrent read support (WAL mode)
- PostgreSQL-compatible query syntax (with minor exceptions)

Schema design must be PostgreSQL-compatible from day one to enable smooth migration.

### Stage 2: PostgreSQL (when required)

Migration triggers:
- Concurrent write volume exceeds SQLite's write concurrency limits
- Multi-node deployment requiring shared state
- Requirement for row-level security or multi-tenancy
- Operational requirement for managed database service (RDS, Cloud SQL)

### Stage 3: Event Streaming (long-term, if required)

For high-volume distributed deployments, an event streaming layer (Redis Streams or a lightweight message queue) between sensors and the database decouples ingestion from storage. This is only needed when ingestion volume exceeds what a single database writer can handle — not a near-term concern.

---

## AI Reasoning Architecture Direction

See [AI_ROADMAP.md](AI_ROADMAP.md) for the full AI integration plan. The architectural requirements it places on the data layer:

1. **Queryable event store:** AI reasoning requires the ability to retrieve events by time window, source IP, event type, ASN, or campaign cluster. This requires SQL, not JSONL scan.

2. **Structured event schema:** LLM prompting is most effective when the data has consistent, typed fields. Untyped dicts produce inconsistent results.

3. **Behavioral fingerprint storage:** Campaign recognition requires a separate table storing derived behavioral signatures, not just raw events.

4. **Async processing:** AI analysis must run asynchronously to avoid blocking the API. A background task queue (FastAPI `BackgroundTasks` initially, Celery or asyncio worker later) is required.

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
| SQLite | Phase 1 onward | Zero infra, immediate |
| Alembic migrations | Phase 1 | Required before schema evolves |
| Background task worker | Phase 5 (AI) | FastAPI BackgroundTasks initially |
| Redis (optional) | Phase 7 (Federation) | Session store, rate limiting, pub/sub |
| PostgreSQL | High-volume scale-out | When SQLite limits are reached |
| Reverse proxy (Caddy/nginx) | Production deployment | TLS termination, rate limiting |
| Object storage (MinIO/S3) | Long-term | PCAP storage, large artifact storage |
| Local LLM runtime (Ollama) | Phase 5 (AI) | Air-gapped deployment requirement |

---

*Cross-references: [ROADMAP.md](ROADMAP.md) · [AI_ROADMAP.md](AI_ROADMAP.md) · [SECURITY_AUDIT.md](SECURITY_AUDIT.md) · [FEDERATION_VISION.md](FEDERATION_VISION.md)*
