# LegionTrap TI — Event Ingestion Pipeline

**Document type:** Implementation blueprint — ingestion API and normalization pipeline
**Audience:** Engineers, autonomous agents, contributors
**Last reviewed:** 2026-05-25
**Status:** Phase 2 implemented. `POST /api/ingest` is live in `app/routers/ingest.py`. Stage 5 (GeoIP enrichment) is deferred to Phase 3.

---

## Overview

The ingestion pipeline is the boundary between the outside world and the LegionTrap event store. Everything that enters the system crosses this boundary. Its job is to:

1. Authenticate the sender
2. Validate the structure of incoming data
3. Normalize heterogeneous sensor formats into a canonical schema
4. Enrich with GeoIP and ASN context
5. Deduplicate against existing records
6. Persist to SQLite and append to the JSONL replica
7. Return a structured receipt

This pipeline is implemented in `app/routers/ingest.py` and `app/utils/`. It depends on the SQLite schema from [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) being in place (Phase 1 — complete).

---

## Endpoint Specification

### `POST /api/ingest`

**Authentication:** API key only (`x-api-key` header). JWT is not appropriate for machine-to-machine sensor ingestion. The existing `require_api_key` dependency is reused.

**Request:**
```http
POST /api/ingest
x-api-key: <API_KEY>
Content-Type: application/json

{
  "events": [
    {
      "id": "48bd03ac-da86-4a4a-8f21-ec4fb0148b76",
      "ts": "2025-10-28T18:31:08.354152+00:00",
      "source": "cowrie",
      "type": "auth_failed",
      "data": {
        "username": "root",
        "password": "badpass1",
        "ip": "203.0.113.2"
      }
    }
  ]
}
```

**Response — success:**
```json
{
  "batch_id": "uuid",
  "accepted": 1,
  "rejected": 0,
  "duplicate": 0,
  "errors": []
}
```

**Response — partial failure:**
```json
{
  "batch_id": "uuid",
  "accepted": 498,
  "rejected": 2,
  "duplicate": 0,
  "errors": [
    {"index": 3, "reason": "missing required field: ts"},
    {"index": 201, "reason": "invalid ip address: not-an-ip"}
  ]
}
```

**Constraints:**
- Maximum batch size: 500 events per request
- Maximum request body: 5 MB (enforced at FastAPI middleware level)
- Partial batches succeed: if 498 of 500 events are valid, 498 are accepted
- Never fail an entire batch because of one bad event
- Rate limit: 1000 requests/minute per API key (via `slowapi`)

---

## Pipeline Stages

```
POST /api/ingest
      │
      ▼
┌─────────────────────────────────────────┐
│ Stage 1: Authentication                 │
│   require_api_key dependency            │
│   → 401 if missing or invalid           │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ Stage 2: Input Validation               │
│   Pydantic RawEvent model               │
│   → 400 if malformed JSON               │
│   → 413 if oversized                    │
│   Missing id → generate UUID            │
│   Missing ts → reject event             │
│   Missing type → reject event           │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ Stage 3: Normalization                  │
│   extract_src_ip()                      │
│   normalize_event_type()                │
│   parse_timestamp()                     │
│   → produce HoneypotEvent               │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ Stage 4: Deduplication                  │
│   SELECT id FROM raw_events WHERE id=?  │
│   → skip if exists (idempotent)         │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ Stage 5: GeoIP Enrichment (Phase 3)     │
│   geoip2 lookup on src_ip               │
│   → country_code, country_name, city    │
│   → asn, asn_org                        │
│   → produce EnrichedEvent               │
│   (skipped if src_ip is None)           │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ Stage 6: Persistence                    │
│   INSERT INTO raw_events                │
│   INSERT INTO events                    │
│   UPSERT INTO source_ips               │
│   APPEND TO storage/events.jsonl        │
│   (best-effort replica; failure does    │
│    not fail the ingest)                 │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│ Stage 7: Audit Log                      │
│   INSERT INTO audit_log                 │
│   event_type='ingest_batch'             │
│   detail={accepted, rejected, batch_id} │
└─────────────────┬───────────────────────┘
                  │
                  ▼
       Return IngestReceipt response
```

---

## Normalization Functions

All normalization logic belongs in `app/utils/event_utils.py`. This module has no FastAPI imports and can be unit-tested in isolation.

### `extract_src_ip(event_dict: dict) -> str | None`

Extracts a valid public IPv4 address from an event dictionary using a defined priority order. Returns `None` if no valid public IP is found.

**Priority order:**
```python
CANDIDATE_FIELDS = [
    ("data", "ip"),         # Cowrie nested format
    ("data", "src_ip"),     # alternative Cowrie/Dionaea
    ("src_ip",),            # flat format
    ("ip",),                # minimal flat format
    ("client_ip",),         # HTTP honeypot format
    ("source_ip",),         # generic sensor format
]
```

For each candidate:
1. Extract the value from the dict (handling nested paths)
2. Validate it is a syntactically valid IPv4 address
3. Validate it is a public IP (not RFC1918, loopback, link-local, or reserved)
4. If valid, return it

If no candidate yields a valid public IP, return `None`. This is not a validation failure — events without a recoverable IP are accepted and stored with `src_ip=NULL`.

**Important:** This function replaces the broken inline IP extraction in `stats.py` (which searched only top-level fields and returned `0` unique IPs for all real Cowrie events). It is the single canonical source of IP extraction logic.

### `normalize_event_type(raw_type: str, source: str) -> str`

Maps sensor-specific event type strings to canonical `event_types.id` values.

```python
TYPE_MAP = {
    "cowrie": {
        "cowrie.login.failed": "auth_failed",
        "cowrie.login.success": "auth_success",
        "cowrie.command.input": "command_exec",
        "cowrie.session.file_upload": "malware_upload",
    },
    "dionaea": {
        "dionaea.connection.free": "port_scan",
    }
}

def normalize_event_type(raw_type: str, source: str) -> str:
    return TYPE_MAP.get(source, {}).get(raw_type, raw_type.lower().replace(".", "_"))
```

If a type is not in the map, it is lowercased and dots replaced with underscores. Unknown types are stored as-is; they can always be re-mapped later by updating the `event_types` table.

### `parse_timestamp(ts_value: Any) -> datetime | None`

Parses timestamps in multiple formats (ISO8601 with and without timezone, Unix timestamps). Returns a timezone-aware UTC datetime or `None` if unparseable.

```python
def parse_timestamp(ts_value: Any) -> datetime | None:
    if ts_value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None
```

---

## Pydantic Models

Full model definitions are in [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md). The ingestion pipeline uses:

### `RawEvent` — input validation boundary

```python
class RawEvent(BaseModel):
    model_config = ConfigDict(extra="allow")  # accept any field from any sensor

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: str                      # validated to parseable datetime in normalization
    source: str
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
```

`extra="allow"` — accept unknown fields without rejection. LegionTrap stores them in `raw_json` and ignores them during normalization. This is intentional: sensors evolve; the ingestion boundary must not break when a sensor adds a new field.

### `HoneypotEvent` — post-normalization canonical form

```python
class HoneypotEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    ts: datetime
    ingested_at: datetime   # written to raw_events.ingested_at; not in the events table
    source: str             # written to raw_events.source; not in the events table
    event_type: str
    src_ip: str | None = None
    dst_port: int | None = None
    protocol: str | None = None
    service: str | None = None
    schema_version: int = 1
```

`ingested_at` and `source` are carried on `HoneypotEvent` so the pipeline can populate `raw_events` from a single object, but `insert_event()` writes only the columns present in the `events` table (see DATABASE_SCHEMA.md). The Phase 3 `EnrichedEvent` extends this model with `country_code`, `country_name`, `city`, `asn`, and `asn_org` fields.

### `IngestRequest` — request body wrapper

```python
class IngestRequest(BaseModel):
    events: list[RawEvent] = Field(..., min_length=1, max_length=500)
```

### `IngestReceipt` — response

```python
class IngestReceipt(BaseModel):
    batch_id: str
    accepted: int
    rejected: int
    duplicate: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
```

---

## Repository Interface

`app/db/repository.py` exposes the storage methods the ingestion pipeline calls. No SQL appears outside this file.

```python
class EventRepository:

    def insert_raw_event(self, raw: RawEvent) -> None:
        """Insert into raw_events. Raises IntegrityError on duplicate id."""

    def insert_event(self, event: HoneypotEvent | EnrichedEvent) -> None:
        """Insert into events table."""

    def upsert_source_ip(self, ip: str, ts: datetime, country_code: str | None,
                         country_name: str | None, asn: int | None,
                         asn_org: str | None) -> None:
        """UPSERT into source_ips, incrementing event_count."""

    def event_exists(self, event_id: str) -> bool:
        """Return True if event_id already exists in raw_events."""

    # Read methods (used by existing routers after Phase 1 migration to SQLite)

    def get_stats(self) -> dict:
        """Return total_events, unique_ips, last_24h counts."""

    def list_events(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Return most recent events, newest first."""

    def get_unique_public_ips(self) -> list[str]:
        """Return sorted list of unique public source IPs (for IOC export)."""
```

---

## GeoIP Enrichment (Phase 3)

GeoIP enrichment runs synchronously during ingestion. `GeoLite2-City.mmdb` is present in `storage/` and the `geoip2` library is already installed. `GeoLite2-ASN.mmdb` must be downloaded separately from MaxMind (free registration required) and placed in `storage/` before ASN enrichment will function.

```python
# app/utils/geoip.py

import geoip2.database
from pathlib import Path

_city_reader = None
_asn_reader = None

def get_city_reader():
    global _city_reader
    if _city_reader is None:
        _city_reader = geoip2.database.Reader("storage/GeoLite2-City.mmdb")
    return _city_reader

def enrich_ip(ip: str) -> dict:
    """Return country_code, country_name, city, asn, asn_org for a public IP."""
    result = {}
    try:
        city = get_city_reader().city(ip)
        result["country_code"] = city.country.iso_code
        result["country_name"] = city.country.name
        result["city"] = city.city.name
    except Exception:
        pass
    # ASN lookup omitted until GeoLite2-ASN.mmdb is confirmed present
    return result
```

GeoIP lookup is a local file read — sub-millisecond, no network call, no privacy concern. It can run synchronously without meaningful performance impact.

---

## Deduplication

Deduplication is based on the `id` field in `raw_events`. The check is a primary key lookup:

```python
def event_exists(self, event_id: str) -> bool:
    row = self.conn.execute(
        "SELECT 1 FROM raw_events WHERE id = ? LIMIT 1", (event_id,)
    ).fetchone()
    return row is not None
```

If an event with the same `id` arrives again (sensor retry, re-import of JSONL), it is silently skipped and counted in `duplicate` in the receipt. The batch continues processing remaining events.

---

## Error Handling

### Validation failure
A `RawEvent` that fails Pydantic validation is rejected. The index of the failing event in the request batch, plus the validation error message, are included in the `errors` array of the response. Processing continues with the next event.

### IP extraction failure
If `extract_src_ip()` finds no valid public IP, the event is accepted with `src_ip=NULL`. This is not a rejection — many valid events lack a source IP.

### GeoIP failure
If the GeoIP database lookup raises any exception (IP not in database, corrupted database), the enrichment is silently skipped. The event is accepted with `NULL` GeoIP fields. GeoIP failures must not cause ingestion failures.

### Database error
If the SQLite insert fails (disk full, I/O error, schema mismatch), the exception propagates to a 500 response for the entire batch. This is the only scenario that fails a whole batch. The JSONL append is not performed if the database write fails — the replica must not diverge from the database.

### Timestamp failure
If `parse_timestamp()` returns `None` (unparseable `ts` field), the event is rejected. Timestamp is a required field for the time-series queries the system depends on.

---

## Security Considerations

### API key only — no JWT for ingestion

Sensor processes (cron jobs, scripts, honeypot processes) must use API key authentication for `POST /api/ingest`. JWT tokens are short-lived (1 hour) and require a login flow — inappropriate for long-running sensor processes. API keys are persistent and suitable for machine-to-machine use.

This is enforced at the route level:
```python
@router.post("/api/ingest", dependencies=[Depends(require_api_key)])
```

### `data.password` must not be extracted

Real Cowrie events include attacker-submitted credentials in `data.password` and `data.username`. These fields:
- Are stored verbatim in `raw_events.raw_json`
- Must **not** be extracted to the `events` table
- Must **not** appear in API responses
- Must **not** appear in AI prompts
- Are attacker-controlled strings and must be treated as untrusted content

The normalization pipeline must explicitly exclude `data.password` from the fields it examines.

### Prompt injection via event data

Attacker-controlled strings in event data (usernames, passwords, User-Agent strings) could contain prompt injection content if they reach an AI prompt. Mitigation:

- The normalization pipeline extracts only typed, structured fields (`src_ip`, `event_type`, `ts`, `dst_port`, `protocol`) — not free-text attacker content
- The AI context builder (Phase 5) uses pre-aggregated SQL summaries, not raw event field values
- `data.password` and `data.username` are never included in AI prompts under any circumstances

### Rate limiting

`slowapi` rate limiter is applied to `POST /api/ingest` at 1000 requests/minute per API key. This prevents a misconfigured sensor from overwhelming the ingestion endpoint. Rate limits on `/api/login` (5 req/min per IP) are separate and must be implemented simultaneously.

---

## JSONL Append Replica

After every successful SQLite write, the normalized event is appended to `storage/events.jsonl`:

```python
def _append_to_jsonl_replica(event: HoneypotEvent) -> None:
    with open("storage/events.jsonl", "a", encoding="utf-8") as f:
        f.write(event.model_dump_json() + "\n")
```

This append is best-effort: if it fails (disk full, permissions error), it is logged but does not cause the ingest to fail. The database write is the authoritative action; the JSONL write is the safety net.

---

## Testing Requirements

Before Phase 2 is considered complete, the following tests must pass:

| Test | Assertion |
|---|---|
| `test_ingest_single_cowrie_event` | POST a real Cowrie event; assert 200, `accepted=1`, event in database |
| `test_ingest_extracts_nested_ip` | POST `{"data": {"ip": "1.2.3.4"}}` event; assert `src_ip="1.2.3.4"` in events table |
| `test_ingest_batch_partial_failure` | POST 5 events, 1 missing `ts`; assert `accepted=4, rejected=1, errors=[...]` |
| `test_ingest_deduplication` | POST same event twice; assert `accepted=1, duplicate=1` on second call |
| `test_ingest_oversized_batch` | POST 501 events; assert 422 or 413 |
| `test_ingest_requires_api_key` | POST without `x-api-key`; assert 401 |
| `test_ingest_jwt_rejected` | POST with Bearer JWT only; assert 401 |
| `test_password_not_in_events_table` | POST Cowrie event with password; assert `data.password` not in events row |
| `test_stats_after_ingest_shows_ip` | Ingest event with IP; assert `GET /api/stats` returns `unique_ips >= 1` |

---

*Cross-references: [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) · [AI_REASONING_ARCHITECTURE.md](AI_REASONING_ARCHITECTURE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md)*
