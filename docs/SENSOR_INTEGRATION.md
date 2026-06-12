# Sensor Integration Guide

> How to connect a real honeypot to the LegionTrap TI ingestion pipeline.

This guide is for operators who have a running LegionTrap instance and want to
forward events from a live honeypot sensor. It covers the canonical API format,
per-sensor mapping notes, historical backfill, and continuous forwarding.

---

## Safety notice

`POST /api/ingest` writes to the operational database. This guide assumes you have
a running LegionTrap deployment and a real sensor producing live attack traffic. Do
not forward real sensor data to a test instance you also use for demos unless that
is your intent.

GeoIP enrichment runs automatically on ingestion when the MaxMind databases are
present in `storage/`. This is a local file lookup — no network call, no privacy
impact.

---

## Prerequisites

- LegionTrap running and accessible (`make run` → API on :8088)
- `API_KEY` set in `.env`
- Sensor deployed and producing log output
- GeoIP databases in `storage/` for geographic enrichment (optional — see README)

---

## Canonical API format

All events enter through `POST /api/ingest`. The request body must be a JSON object
with an `events` array. Each event requires `ts`, `source`, and `type`.

```http
POST /api/ingest HTTP/1.1
x-api-key: <your-API_KEY>
Content-Type: application/json

{
  "events": [
    {
      "id": "48bd03ac-da86-4a4a-8f21-ec4fb0148b76",
      "ts": "2025-10-28T18:31:08.354152+00:00",
      "source": "cowrie",
      "type": "cowrie.login.failed",
      "data": {
        "ip": "203.0.113.2",
        "username": "root",
        "password": "badpass1"
      }
    }
  ]
}
```

**Field notes:**

| Field | Required | Description |
|-------|:--------:|-------------|
| `id` | No | UUID for this event. Auto-generated if omitted. Provide a stable per-event ID to enable deduplication across retries. |
| `ts` | **Yes** | ISO 8601 timestamp with timezone offset (e.g., `2025-10-28T18:31:08+00:00`). Unix epoch integers are also accepted. |
| `source` | **Yes** | Sensor identifier string (e.g., `"cowrie"`, `"opencanary"`). |
| `type` | **Yes** | Event type string. Sensor-native strings are accepted and normalized internally. |
| `data` | No | Sensor-specific fields dict. Additional top-level fields outside `data` are also accepted. |

**Limits:** 500 events per request, 5 MB max body, 1000 requests/minute per API key.

**Response:**
```json
{
  "batch_id": "uuid",
  "accepted": 1,
  "rejected": 0,
  "duplicate": 0,
  "errors": []
}
```

Batches are processed event by event — if some events fail validation, the valid ones
are still accepted. See [docs/INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) for the
full contract.

---

## Sensor-specific guides

### Cowrie SSH/Telnet honeypot — VERIFIED

Support status: **VERIFIED** — explicit type mapping, IP extraction priority, and
integration test coverage confirm this path end to end.

Cowrie writes newline-delimited JSON events to `var/log/cowrie/cowrie.json` (and
dated rotation files). Each line is one event.

**Native Cowrie log line:**
```json
{
  "eventid": "cowrie.login.failed",
  "timestamp": "2025-10-28T18:31:08.354152+00:00",
  "session": "a3b4c5d6e7f8",
  "src_ip": "203.0.113.2",
  "src_port": 49212,
  "username": "root",
  "password": "badpass1",
  "sensor": "my-honeypot"
}
```

**Mapped to LegionTrap format:**
```json
{
  "events": [{
    "id": "a3b4c5d6e7f8-login-failed",
    "ts": "2025-10-28T18:31:08.354152+00:00",
    "source": "cowrie",
    "type": "cowrie.login.failed",
    "data": {
      "ip": "203.0.113.2",
      "username": "root",
      "password": "badpass1"
    }
  }]
}
```

**Mapping notes:**
- `ts` ← Cowrie `timestamp`
- `type` ← Cowrie `eventid` (passed through as-is)
- `data.ip` ← Cowrie `src_ip` — put the attacker IP here; `data.ip` has the highest
  extraction priority in LegionTrap's normalization pipeline

**Known Cowrie type mappings** (normalized internally by LegionTrap):

| Cowrie `eventid` | Stored canonical type |
|---|---|
| `cowrie.login.failed` | `auth_failed` |
| `cowrie.login.success` | `auth_success` |
| `cowrie.command.input` | `command_exec` |
| `cowrie.session.file_upload` | `malware_upload` |

Other Cowrie event types are lowercased with dots replaced by underscores and stored
as-is (e.g., `cowrie.session.connect` → `cowrie_session_connect`).

**Example curl:**
```bash
curl -s -X POST http://127.0.0.1:8088/api/ingest \
  -H "x-api-key: <your-API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "ts": "2025-10-28T18:31:08.354152+00:00",
      "source": "cowrie",
      "type": "cowrie.login.failed",
      "data": {
        "ip": "203.0.113.2",
        "username": "root",
        "password": "badpass1"
      }
    }]
  }' | python -m json.tool
```

---

### OpenCanary — PARTIAL/INFERRED (field names may vary by version and event type)

Support status: **PARTIAL/INFERRED** — accepted by the API via the `extra="allow"`
policy on `RawEvent`; no native type mapping in LegionTrap; field extraction depends
on how you structure the payload before forwarding.

OpenCanary logs use integer `logtype` codes (e.g., `2000` = SSH brute force) and a
`logdata` dict for event-specific fields. The API accepts OpenCanary events, but you
must perform field mapping in a forwarding script before posting.

**Native OpenCanary log line:**
```json
{
  "dst_host": "192.168.1.100",
  "dst_port": 22,
  "local_time_adjusted": "2025-10-28T18:31:08.354152",
  "logdata": {"USERNAME": "pi", "PASSWORD": "raspberry"},
  "logtype": 2000,
  "src_host": "203.0.113.5",
  "src_port": 49212
}
```

**Mapped to LegionTrap format:**
```json
{
  "events": [{
    "ts": "2025-10-28T18:31:08.354152+00:00",
    "source": "opencanary",
    "type": "canary.ssh.login",
    "data": {
      "ip": "203.0.113.5",
      "username": "pi",
      "password": "raspberry"
    }
  }]
}
```

**Mapping notes:**
- `ts` ← `local_time_adjusted` with an explicit `+00:00` suffix if no timezone is
  present in the OpenCanary output
- `type` ← derive a descriptive string from `logtype` (no standard LegionTrap mapping
  exists; use a consistent scheme such as `canary.ssh.login`, `canary.telnet.login`)
- `data.ip` ← `src_host` — placing the IP in `data.ip` ensures the highest extraction
  priority
- `data.username`, `data.password` ← extracted from `logdata`

Alternatively, passing `src_ip` at the top level (outside `data`) also works —
LegionTrap checks several candidate field names during extraction. Placing the IP in
`data.ip` is preferred.

A mapping script for OpenCanary is not bundled with LegionTrap. Write a conversion
step that matches the specific OpenCanary version and event types in your deployment.

---

### T-Pot — PARTIAL/SENSOR-DEPENDENT

Support status: **PARTIAL/SENSOR-DEPENDENT** — Cowrie events exported from T-Pot
follow the Cowrie path above and are VERIFIED; other T-Pot bundled sensors require
their own field mappings.

T-Pot is a multi-sensor honeypot aggregator that bundles Cowrie alongside Honeytrap,
Glutton, Dionaea, and others. Events are collected internally via an Elasticsearch
stack.

If you extract Cowrie events from T-Pot's Elasticsearch or file output, the Cowrie
section applies directly — the `eventid`, `timestamp`, and `src_ip` fields are
identical to standalone Cowrie.

For other T-Pot bundled sensors:
- **Dionaea:** LegionTrap maps `dionaea.connection.free` → `port_scan`.
- **Other sensors:** accepted as raw events via `extra="allow"`, but type mapping and
  IP extraction depend on each sensor's native output format. Test with a single event
  and verify the ingested `src_ip` and `event_type` values via `GET /api/events`.

---

## Historical backfill via import_jsonl.py

For importing existing log archives rather than forwarding live events, use
`scripts/import_jsonl.py`. It processes JSONL files (one event per line) using the
same `RawEvent` schema as `POST /api/ingest` and is idempotent — events with a
duplicate `id` are silently skipped.

**JSONL line format:**
```json
{"id":"48bd03ac-da86-4a4a-8f21-ec4fb0148b76","ts":"2025-10-28T18:31:08+00:00","source":"cowrie","type":"cowrie.login.failed","data":{"ip":"203.0.113.2","username":"root","password":"bad"}}
```

Fields `id`, `ts`, `source`, and `type` are required on each line. `data` is optional.

**Usage:**
```bash
# Import a single file
python scripts/import_jsonl.py storage/events-2025-10.jsonl

# Import a set of files (via Makefile target)
make import-jsonl JSONL_FILES="storage/events-*.jsonl"
```

**Important:** `import_jsonl.py` does not perform GeoIP enrichment. Country, city, and
ASN fields will be NULL for all backfilled events. Live ingest via `POST /api/ingest`
enriches in real time when the MaxMind databases are present in `storage/`.

---

## Continuous forwarding pattern

For live sensor traffic, the general forwarding approach is:

1. Watch the sensor's JSON log output (e.g., `tail -F var/log/cowrie/cowrie.json`).
2. Convert each new log line to the LegionTrap RawEvent format (see sensor sections
   above).
3. POST to `/api/ingest` in batches — up to 500 events per request.
4. Use a stable per-event `id` derived from the sensor's native event identifier so
   that re-sending events on restart does not create duplicates.

For Cowrie, a stable ID can be derived from the `session` identifier combined with the
`eventid` and timestamp. If Cowrie is configured to emit a UUID field, use it directly.

---

## Troubleshooting

**`401 Unauthorized`**
The `x-api-key` header is missing or does not match `API_KEY` in `.env`.

**`422 Unprocessable Entity`**
One or more required fields are missing or malformed. Check that:
- `ts`, `source`, and `type` are present on every event
- `ts` is a valid ISO 8601 string or Unix epoch integer
- The request body is wrapped in `{"events": [...]}`

**`src_ip` is NULL after ingestion**
The source IP was not found in an expected field. Ensure the IP is in `data.ip`,
`data.src_ip`, or at the top level as `src_ip`. Check the extraction priority list in
`app/utils/event_utils.py`.

**`src_ip` is NULL for private addresses**
RFC1918, loopback, and link-local IPs pass validation but are stored as NULL because
they fail the public-IP check. These addresses are filtered from IOC exports.

**Events accepted but not appearing in campaigns**
Campaign clustering runs after each ingest batch. A source IP requires multiple events
across several dimensions before its fingerprint is confident enough to cluster. Ingest
several events from the same source IP and check `GET /api/campaigns`.

---

## Privacy notes

- Passwords captured by Cowrie (or any sensor) are stored verbatim in the `raw_events`
  table as part of `raw_json`. They do not appear in the `events` table or in API
  responses. Consider your retention policy for credential data before ingesting at
  scale.
- `PRIVACY_MODE=on` masks IP addresses on IOC exports — it does not affect what is
  stored in the database.
- See the README [Privacy & Anonymization](../README.md#privacy--anonymization) section
  for full detail on IP masking options.

---

## Further reading

- [docs/INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) — full API contract, normalization pipeline, field semantics, and error handling
- [README.md Quick Start](../README.md#quick-start-local) — API key setup, GeoIP setup, health check, and test ingest example
