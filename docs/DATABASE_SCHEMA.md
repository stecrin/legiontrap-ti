# LegionTrap TI — Database Schema

**Document type:** Implementation blueprint — canonical SQL schema reference
**Audience:** Engineers, autonomous agents, Alembic migration authors
**Last reviewed:** 2026-05-23
**Status:** Design-complete. Not yet implemented. This document is the source of truth for Phase 1 implementation.

---

## Design Principles

1. **PostgreSQL-compatible from day one.** Use only standard SQL types (`TEXT`, `INTEGER`, `REAL`, `BLOB`). Avoid SQLite-specific extensions. Migration from SQLite to PostgreSQL must require only driver and connection-string changes.
2. **Never mix raw and derived data.** The `raw_events` table is immutable provenance. The `events` table is the analytical surface. Behavioral and AI tables are derived. Federation tables are external. Each layer has a distinct trust level and retention policy.
3. **No SQL in routers.** All database access goes through `app/db/repository.py`. Routers call repository methods. Repository methods call SQL. This abstraction is the migration safety net.
4. **Index for the actual queries.** Every index listed below corresponds to a real query pattern defined in [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) or [AI_REASONING_ARCHITECTURE.md](AI_REASONING_ARCHITECTURE.md).
5. **`schema_version` on every derived table.** Enables selective reprocessing when extraction logic changes.

---

## Storage Location

```
storage/legiontrap.db       # production database
storage/legiontrap-test.db  # test database (created by conftest.py, gitignored)
```

Both paths will be controlled by the `DB_PATH` environment variable (added to `app/core/config.py` in Phase 1). The `storage/` directory is gitignored for `*.db` files. The database file itself is the complete state of the system; backup = copy this file.

Enable WAL mode immediately on connection:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
```

---

## Table Reference

### Dependency order (creation order)

```
event_types
raw_events
source_ips
events                    → raw_events, event_types
behavioral_fingerprints
campaigns                 → behavioral_fingerprints
campaign_events           → campaigns, events
ai_analyses
federation_fingerprints
audit_log
```

---

## Core Event Tables

### `event_types`

Lookup table for the normalized event type taxonomy. Enables ATT&CK mapping without reprocessing events.

```sql
CREATE TABLE event_types (
    id               TEXT PRIMARY KEY,   -- e.g. 'auth_failed', 'port_scan', 'http_probe'
    label            TEXT NOT NULL,      -- human-readable: 'SSH Authentication Failure'
    attack_tactic    TEXT,               -- MITRE ATT&CK tactic: 'Credential Access'
    attack_technique TEXT,               -- MITRE ATT&CK ID: 'T1110.001'
    description      TEXT
);
```

**Initial seed values:**

| id | label | attack_tactic | attack_technique |
|---|---|---|---|
| `auth_failed` | SSH Authentication Failure | Credential Access | T1110.001 |
| `auth_success` | SSH Authentication Success | Initial Access | T1078 |
| `port_scan` | Port Scan Probe | Discovery | T1046 |
| `http_probe` | HTTP Endpoint Probe | Discovery | T1595.002 |
| `malware_upload` | Malware Upload Attempt | Execution | T1204 |
| `command_exec` | Remote Command Execution | Execution | T1059 |
| `unknown` | Unknown Event Type | — | — |

New event types can be inserted without schema migration.

---

### `raw_events`

Immutable provenance record. Stores the original JSON exactly as received from the sensor. Never modified after insert. Never exposed through any API endpoint.

```sql
CREATE TABLE raw_events (
    id           TEXT PRIMARY KEY,   -- UUID from sensor, or generated on ingest
    ts           TEXT NOT NULL,      -- ISO8601 with timezone, as received
    ingested_at  TEXT NOT NULL,      -- datetime LegionTrap received the event (UTC)
    source       TEXT NOT NULL,      -- 'cowrie', 'dionaea', 'custom', etc.
    raw_json     TEXT NOT NULL       -- original JSON line verbatim
);

CREATE INDEX idx_raw_events_ts     ON raw_events(ts);
CREATE INDEX idx_raw_events_source ON raw_events(source);
CREATE INDEX idx_raw_events_ingested ON raw_events(ingested_at);
```

**Retention policy:** Subject to `DATA_RETENTION_DAYS` setting. When a raw event is deleted by retention, the corresponding `events` row is also deleted. Behavioral fingerprints and campaigns are **not** subject to retention — they outlive the raw data they were derived from.

---

### `events`

The primary analytical table. Every dashboard query, every AI query, every behavioral query runs against this table. Populated by the normalization pipeline from `raw_events`.

```sql
CREATE TABLE events (
    id             TEXT PRIMARY KEY,  -- FK to raw_events.id
    ts             TEXT NOT NULL,     -- normalized ISO8601 UTC
    src_ip         TEXT,              -- extracted, validated public IPv4 (nullable)
    dst_port       INTEGER,
    protocol       TEXT,              -- 'tcp', 'udp'
    event_type     TEXT NOT NULL,     -- FK to event_types.id
    service        TEXT,              -- 'ssh', 'http', 'ftp', 'telnet'
    country_code   TEXT,              -- ISO 3166-1 alpha-2 (from GeoIP, Phase 3)
    country_name   TEXT,
    city           TEXT,
    asn            INTEGER,           -- ASN number (from GeoIP, Phase 3)
    asn_org        TEXT,              -- ASN organization name
    campaign_id    TEXT,              -- FK to campaigns.id (nullable until Phase 6)
    schema_version INTEGER NOT NULL DEFAULT 1,

    FOREIGN KEY (id)          REFERENCES raw_events(id)  ON DELETE CASCADE,
    FOREIGN KEY (event_type)  REFERENCES event_types(id)
    -- campaign_id FK omitted from Phase 1 DDL: campaigns table does not exist yet.
    -- Added via ALTER TABLE in 0004_behavioral_tables.py (Phase 6).
);

CREATE INDEX idx_events_ts            ON events(ts);
CREATE INDEX idx_events_src_ip        ON events(src_ip);
CREATE INDEX idx_events_type          ON events(event_type);
CREATE INDEX idx_events_asn           ON events(asn);
CREATE INDEX idx_events_country       ON events(country_code);
CREATE INDEX idx_events_campaign      ON events(campaign_id);
CREATE INDEX idx_events_ts_type       ON events(ts, event_type);   -- dashboard trend chart
CREATE INDEX idx_events_ts_src_ip     ON events(ts, src_ip);       -- per-IP timeline
```

**Note on `src_ip`:** Nullable. Not all events have a source IP (e.g., internal alerts, malware upload events where the IP is in a different field). The normalization pipeline extracts `src_ip` via priority field order: `data.ip` → `data.src_ip` → `src_ip` → `ip` → `client_ip` → `source_ip`. See [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) for the full extraction logic.

---

## Source IP Enrichment

### `source_ips`

Denormalized IP intelligence. Updated (upserted) on every new event from a given IP. Eliminates per-request GeoIP lookups by materializing enrichment at ingestion time.

```sql
CREATE TABLE source_ips (
    ip               TEXT PRIMARY KEY,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    event_count      INTEGER NOT NULL DEFAULT 0,
    country_code     TEXT,
    country_name     TEXT,
    asn              INTEGER,
    asn_org          TEXT,
    is_tor_exit      INTEGER NOT NULL DEFAULT 0,  -- BOOLEAN (0/1)
    is_vpn           INTEGER NOT NULL DEFAULT 0,
    reputation_score REAL,                         -- 0.0–1.0 (future enrichment)
    tags             TEXT                          -- JSON array: '["scanner","brute-force"]'
);

CREATE INDEX idx_source_ips_asn       ON source_ips(asn);
CREATE INDEX idx_source_ips_country   ON source_ips(country_code);
CREATE INDEX idx_source_ips_last_seen ON source_ips(last_seen);
CREATE INDEX idx_source_ips_count     ON source_ips(event_count DESC);
```

**Upsert pattern on every ingest:**

```sql
INSERT INTO source_ips (ip, first_seen, last_seen, event_count, country_code,
                        country_name, asn, asn_org)
VALUES (?, ?, ?, 1, ?, ?, ?, ?)
ON CONFLICT(ip) DO UPDATE SET
    last_seen   = excluded.last_seen,
    event_count = event_count + 1;
```

---

## Behavioral Intelligence Tables

These tables are created in Phase 6. The columns are defined here for schema planning purposes; the Alembic migration that creates them is not written until Phase 6 begins.

### `behavioral_fingerprints`

Derived behavioral signatures stored separately from events. Enables campaign matching without re-analyzing raw events. Persists beyond event retention policy.

```sql
CREATE TABLE behavioral_fingerprints (
    id                   TEXT PRIMARY KEY,   -- UUID
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    event_count          INTEGER NOT NULL,
    port_sequence_class  TEXT,      -- 'sequential-ascending', 'targeted', 'random'
    timing_type          TEXT,      -- 'periodic', 'burst', 'slow', 'irregular'
    timing_interval_ms   INTEGER,   -- median inter-probe interval in ms
    timing_jitter_pct    REAL,      -- inter-probe timing jitter as % of interval
    primary_protocol     TEXT,      -- 'SSH', 'HTTP', 'Telnet', 'FTP'
    protocol_variant     TEXT,      -- 'OpenSSH-compatible', 'custom', 'RFC-compliant'
    targeting_category   TEXT,      -- 'credential-brute-force', 'port-scan', 'web-probe'
    asn_count            INTEGER,   -- number of distinct ASNs in the cluster
    geographic_spread    TEXT,      -- 'single-country', 'multi-region', 'global'
    confidence           REAL NOT NULL,   -- 0.0–1.0
    schema_version       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_fp_protocol   ON behavioral_fingerprints(primary_protocol);
CREATE INDEX idx_fp_category   ON behavioral_fingerprints(targeting_category);
CREATE INDEX idx_fp_confidence ON behavioral_fingerprints(confidence);
```

### `campaigns`

Persistent campaign cluster records. A campaign that went dormant months ago is not deleted — it is marked dormant and reactivated when a matching fingerprint is observed again.

```sql
CREATE TABLE campaigns (
    id               TEXT PRIMARY KEY,   -- e.g. 'C-2026-031' (auto-generated)
    fingerprint_id   TEXT,               -- FK to behavioral_fingerprints.id
    label            TEXT,               -- analyst-editable display name
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    dormant_since    TEXT,               -- NULL if active
    event_count      INTEGER NOT NULL DEFAULT 0,
    source_ip_count  INTEGER NOT NULL DEFAULT 0,
    asn_count        INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'active',  -- 'active', 'dormant', 'closed'
    confidence       REAL NOT NULL,
    analyst_notes    TEXT,

    FOREIGN KEY (fingerprint_id) REFERENCES behavioral_fingerprints(id)
);

CREATE INDEX idx_campaigns_status      ON campaigns(status);
CREATE INDEX idx_campaigns_last_seen   ON campaigns(last_seen);
CREATE INDEX idx_campaigns_fingerprint ON campaigns(fingerprint_id);
```

### `campaign_events`

Many-to-many bridge between events and campaigns. An event can be tentatively assigned to multiple campaigns during the clustering phase until confidence resolves.

```sql
CREATE TABLE campaign_events (
    campaign_id  TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    assigned_at  TEXT NOT NULL,
    confidence   REAL NOT NULL,

    PRIMARY KEY (campaign_id, event_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id)    REFERENCES events(id)    ON DELETE CASCADE
);

CREATE INDEX idx_ce_campaign ON campaign_events(campaign_id);
CREATE INDEX idx_ce_event    ON campaign_events(event_id);
```

---

## AI Analysis Results

### `ai_analyses`

Immutable record of every AI analysis performed. Provides audit trail and enables feeding historical analysis context into future AI queries.

```sql
CREATE TABLE ai_analyses (
    id                  TEXT PRIMARY KEY,   -- UUID
    created_at          TEXT NOT NULL,
    window_start        TEXT,               -- analysis time window start (nullable for ad-hoc)
    window_end          TEXT,
    backend             TEXT NOT NULL,      -- 'claude', 'ollama', 'none'
    model               TEXT,               -- model identifier string
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    summary             TEXT NOT NULL,      -- narrative analysis text
    key_findings        TEXT,               -- JSON array of strings
    recommended_actions TEXT,               -- JSON array of strings
    confidence          TEXT NOT NULL,      -- 'low', 'medium', 'high'
    campaign_ids        TEXT,               -- JSON array of referenced campaign IDs
    schema_version      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_ai_created  ON ai_analyses(created_at);
CREATE INDEX idx_ai_backend  ON ai_analyses(backend);
CREATE INDEX idx_ai_window   ON ai_analyses(window_start, window_end);
```

**Privacy constraint:** `ai_analyses` must never store raw event content. It stores only narrative text, campaign IDs, and metadata. Raw IPs appearing in AI output summaries are subject to the same masking rules as IOC exports when `PRIVACY_MODE` is active.

---

## Federation Tables

### `federation_fingerprints`

Received behavioral fingerprints from federated peers. Kept strictly separate from locally-derived fingerprints — they have different provenance, trust levels, and retention policies.

```sql
CREATE TABLE federation_fingerprints (
    fingerprint_id          TEXT PRIMARY KEY,
    received_at             TEXT NOT NULL,
    contributor_id          TEXT NOT NULL,  -- pseudonymous deployment hash (never real identity)
    schema_version          TEXT NOT NULL,
    observed_at             TEXT NOT NULL,
    signature               TEXT NOT NULL,  -- base64-encoded Ed25519 signature
    dimensions_json         TEXT NOT NULL,  -- full fingerprint JSON blob
    confidence              REAL NOT NULL,
    event_count             INTEGER,
    matched_local_campaign  TEXT,           -- FK to campaigns.id if a match was found
    trust_tier              TEXT NOT NULL DEFAULT 'peer'  -- 'peer', 'circle', 'public'
);

CREATE INDEX idx_fed_contributor ON federation_fingerprints(contributor_id);
CREATE INDEX idx_fed_received    ON federation_fingerprints(received_at);
CREATE INDEX idx_fed_tier        ON federation_fingerprints(trust_tier);
```

---

## Audit Log

### `audit_log`

Structured log of security-relevant events. Required for any deployment handling real security telemetry. Never deleted by event retention policy — has its own configurable retention period (default 90 days).

```sql
CREATE TABLE audit_log (
    id          TEXT PRIMARY KEY,   -- UUID
    ts          TEXT NOT NULL,
    event_type  TEXT NOT NULL,      -- 'auth_success', 'auth_failure', 'ioc_export',
                                    -- 'ai_call', 'ingest_batch', 'federation_receive'
    auth_method TEXT,               -- 'jwt', 'api_key', null for unauthenticated
    source_ip   TEXT,               -- client IP (nullable; not always available)
    detail      TEXT                -- JSON with non-sensitive context only
);

CREATE INDEX idx_audit_ts         ON audit_log(ts);
CREATE INDEX idx_audit_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_source_ip  ON audit_log(source_ip);
```

---

## Migration Management

Alembic manages all schema changes. The migration version table is created by Alembic automatically (`alembic_version`).

**Migration naming convention:**

```
app/db/migrations/versions/
  0001_initial_schema.py        -- creates all Phase 1 tables
  0002_add_geoip_fields.py      -- Phase 3: adds country/ASN fields to events
  0003_ai_analysis_table.py     -- Phase 5: adds ai_analyses
  0004_behavioral_tables.py     -- Phase 6: adds fingerprints, campaigns, campaign_id FK
  0005_federation_table.py      -- Phase 7: adds federation_fingerprints
```

**Rule:** Never manually ALTER a table that Alembic manages. All schema changes go through a new migration file.

---

## Schema Evolution Policy

| Table | When created | Retention | Can be deleted by policy? |
|---|---|---|---|
| `event_types` | Phase 1 | Permanent | No |
| `raw_events` | Phase 1 | `DATA_RETENTION_DAYS` | Yes |
| `events` | Phase 1 | `DATA_RETENTION_DAYS` | Yes (with raw_events) |
| `source_ips` | Phase 1 | Permanent | No (intelligence asset) |
| `behavioral_fingerprints` | Phase 6 | Permanent | No (outlives events) |
| `campaigns` | Phase 6 | Permanent | No (outlives events) |
| `campaign_events` | Phase 6 | With `events` | Yes (CASCADE) |
| `ai_analyses` | Phase 5 | Separate (90d default) | Yes |
| `federation_fingerprints` | Phase 7 | Separate configurable | Yes |
| `audit_log` | Phase 1 | Separate (90d default) | Yes |

---

*Cross-references: [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) · [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) · [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md)*
