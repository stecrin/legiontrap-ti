# LegionTrap TI — Migration Guide

**Document type:** Implementation blueprint — JSONL-to-SQLite migration procedure
**Audience:** Engineers, operators, autonomous agents performing Phase 1 work
**Last reviewed:** 2026-05-23
**Status:** Complete. Phase 1 migration is done. Run `alembic upgrade head` to apply the schema to a new deployment.

---

## Overview

LegionTrap currently stores events in a JSONL flat file (`storage/events.jsonl`). This guide describes the migration from that storage to SQLite, covering:

- Why the migration happens at this point in the roadmap
- What happens to existing JSONL data
- How the migration is executed safely
- How to verify the migration succeeded
- How to roll back if something goes wrong
- What operators upgrading from a JSONL deployment need to do

This migration was a **prerequisite** for all AI features, behavioral memory, campaign detection, and federation. Phase 2 (ingestion API via `POST /api/ingest`) is also complete.

---

## Prerequisites

Before running any migration step, verify:

- [ ] Phase 0 security items are complete (bcrypt password, CORS restricted, no hardcoded defaults)
- [ ] `DB_PATH` is set in `.env` (or defaults to `storage/legiontrap.db`)
- [ ] `storage/` directory exists and is writable
- [ ] `storage/events.jsonl` exists (may be empty or contain historical events)
- [ ] Alembic is installed: `.venv/bin/alembic --version`
- [ ] A backup of `storage/events.jsonl` exists before migration begins

---

## What Happens to the JSONL File

**The JSONL file is never deleted.**

After migration it transitions from the primary data store to two ongoing roles:

1. **Append-only replica:** After every successful ingest via `POST /api/ingest`, the normalized event is also appended to `storage/events.jsonl`. The file remains a consistent recovery point. If the SQLite database is lost or corrupted, it can be fully reconstructed by re-importing the JSONL file.

2. **Import/export format:** External tools (Cowrie, Dionaea, other sensors) that write directly to the JSONL file continue to work during the transition. A background JSONL watcher (Phase 2+) will pick up new lines and ingest them into SQLite.

The file is the safety net. It must never be removed.

---

## Migration Architecture

```
BEFORE MIGRATION                    AFTER MIGRATION
─────────────────────────────       ─────────────────────────────────────────
storage/events.jsonl                storage/events.jsonl  (append-only replica)
    │                                   │
    │  read on every request             │  append on every ingest
    ▼                                   ▼
FastAPI routers                     storage/legiontrap.db  (primary store)
(full file scan per call)               │
                                        │  indexed SQL queries
                                        ▼
                                    FastAPI routers via EventRepository
                                    (sub-millisecond queries with indexes)
```

---

## Step-by-Step Migration Procedure

### Step 1: Install Alembic and initialize migrations

```bash
# Alembic is added to requirements.txt during Phase 1
pip install alembic

# Initialize the Alembic environment in the project
alembic init app/db/migrations

# alembic.ini is created at project root
# app/db/migrations/env.py is created — update it to point at legiontrap metadata
```

`alembic.ini` database URL:
```ini
sqlalchemy.url = sqlite:///storage/legiontrap.db
```

For test environments, read `DB_PATH` from the environment in `app/db/migrations/env.py`:
```python
import os
db_path = os.environ.get("DB_PATH", "storage/legiontrap.db")
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
```

Set `DB_PATH=storage/legiontrap-test.db` before running `alembic upgrade head` in CI.

### Step 2: Apply the initial schema migration

```bash
alembic upgrade head
```

This creates all Phase 1 tables: `event_types`, `raw_events`, `events`, `source_ips`, `audit_log`. It also seeds `event_types` with the initial taxonomy values.

Verify the database was created:
```bash
sqlite3 storage/legiontrap.db ".tables"
# Expected: audit_log  event_types  events  raw_events  source_ips
```

### Step 3: Import existing JSONL data

```bash
python -m app.tools.import_jsonl storage/events.jsonl
```

If additional archived JSONL files exist (e.g., `storage/events-20251028-183613.jsonl`), import each:
```bash
python -m app.tools.import_jsonl storage/events-20251028-183613.jsonl
python -m app.tools.import_jsonl storage/events-20251028-181245.jsonl
```

The import tool:
- Reads each line of the JSONL file
- Validates against `RawEvent` Pydantic schema
- Normalizes to `HoneypotEvent` (extracts `src_ip` from nested fields)
- Inserts into `raw_events` and `events` (upserts by `id` — safe to re-run)
- Upserts `source_ips` for each extracted IP
- Writes failures to `storage/import_errors.jsonl` (not silently dropped)
- Reports: events accepted, events skipped (duplicate), events failed

**Expected output for a 8,000-event file:**
```
Importing: storage/events-20251028-183613.jsonl
  Accepted:  8000
  Duplicate: 0
  Failed:    0
Import complete. Database: storage/legiontrap.db
```

### Step 4: Verify import correctness

Run the verification query:
```bash
python -m app.tools.verify_migration storage/events-20251028-183613.jsonl
```

The verify tool counts lines in the JSONL file and rows in SQLite and asserts they match. It also checks that `unique_ips` in SQLite matches the count from `iocs_pf.py`'s recursive IP extraction.

### Step 5: Switch read endpoints to SQLite

This is a code change, not a database change. The router implementations are updated to call `EventRepository` methods instead of reading the JSONL file. See [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) for the repository interface.

The API response shapes do not change. Existing clients (dashboard, pfSense scripts) continue working without modification.

### Step 6: Smoke test the migrated endpoints

```bash
# Stats endpoint — verify counts match pre-migration values
curl -H "x-api-key: $API_KEY" http://localhost:8088/api/stats

# Events endpoint — verify newest-first ordering preserved
curl -H "x-api-key: $API_KEY" "http://localhost:8088/api/events?limit=5"

# IOC export — verify IP list matches pre-migration output
curl -H "x-api-key: $API_KEY" http://localhost:8088/api/iocs/pf.conf
```

Compare output against baseline captured before the migration.

### Step 7: Enable JSONL append replica

After confirming the migrated endpoints work correctly, enable the write-through replica in the ingestion pipeline. Every event written to SQLite is simultaneously appended to `storage/events.jsonl`.

---

## Import Tool Specification

`app/tools/import_jsonl.py` is a command-line tool, not a library. It must not be imported by application code.

```
usage: python -m app.tools.import_jsonl <path> [--dry-run] [--batch-size N]

positional arguments:
  path              Path to JSONL file to import

options:
  --dry-run         Parse and validate without inserting (shows what would be imported)
  --batch-size N    Rows per SQLite transaction (default: 500)
  --errors-file F   Path for import error log (default: storage/import_errors.jsonl)
```

**Idempotency:** The import tool uses `INSERT OR IGNORE` on `raw_events` (primary key is the event `id`). Running the same file twice produces the same database state. This means JSONL files can be re-imported after schema changes without risk of duplication.

**Error handling:** Events that fail Pydantic validation are not silently discarded. Each failure is written to the errors file with the original line and the validation error. The import continues — one bad event does not abort the batch.

---

## Handling the Existing Event Schema Mismatch

The real Cowrie events in `storage/events-20251028-183613.jsonl` have this structure:

```json
{
  "id": "48bd03ac-da86-4a4a-8f21-ec4fb0148b76",
  "ts": "2025-10-28T18:31:08.354152+00:00",
  "source": "cowrie",
  "type": "auth_failed",
  "data": {
    "username": "root",
    "password": "px1",
    "ip": "203.0.113.2"
  }
}
```

The IP is nested inside `data.ip`. The import tool's `extract_src_ip()` function (in `app/utils/event_utils.py`) uses this priority order to find it:

```
data.ip → data.src_ip → src_ip → ip → client_ip → source_ip
```

The `data.password` field is intentionally **not** extracted to the `events` table. It remains in `raw_events.raw_json` (the verbatim JSON archive) and is never surfaced through any API endpoint. It is attacker-controlled content and must not appear in AI prompts, IOC exports, or dashboard responses.

---

## Rollback Plan

SQLite is a single file. Rollback is:

```bash
# 1. Stop the application
# 2. Rename or delete the database
mv storage/legiontrap.db storage/legiontrap.db.bak

# 3. Set STORAGE_BACKEND=jsonl in .env (if the env var is implemented)
#    OR revert the router code to JSONL file reading
# 4. Restart the application
```

The JSONL file was never modified during migration. It is the complete event history. Full rollback takes under 30 seconds.

**The JSONL replica ensures the rollback path is always available.** As long as the replica write is working, no event that reached the SQLite database is unavailable in the JSONL file.

---

## Operator Upgrade Procedure (Existing Deployments)

For operators upgrading from a JSONL-only deployment to the SQLite-backed version:

1. **Stop the application**
2. **Back up `storage/events.jsonl`** to a safe location
3. **Update the application** (git pull or image pull)
4. **Install new dependencies:** `pip install -r requirements.txt`
5. **Run the migration:** `alembic upgrade head`
6. **Import existing events:** `python -m app.tools.import_jsonl storage/events.jsonl`
7. **Verify the import:** `python -m app.tools.verify_migration storage/events.jsonl`
8. **Start the application**
9. **Smoke test** the API endpoints
10. **Monitor `storage/import_errors.jsonl`** for any events that failed validation

The migration is additive. No data is destroyed. The original JSONL file is preserved.

---

## Post-Migration Verification Queries

After migration, these queries can be run directly against the database to verify correctness:

```sql
-- Total event count (should match JSONL line count)
SELECT COUNT(*) FROM events;

-- Unique source IPs (should match iocs_pf.py output before migration)
SELECT COUNT(DISTINCT src_ip) FROM events WHERE src_ip IS NOT NULL;

-- Events by source (should show 'cowrie' for the test data)
SELECT source, COUNT(*) FROM raw_events GROUP BY source;

-- Events by type (should show 'auth_failed: 8000' for test data)
SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY COUNT(*) DESC;

-- IP not extracted (events where normalization could not find an IP)
SELECT COUNT(*) FROM events WHERE src_ip IS NULL;
```

The last query is particularly important. Before migration, `stats.py` returned `unique_ips: 0` for real Cowrie events because it searched only top-level fields. After migration with the corrected `extract_src_ip()` logic, `unique_ips` should reflect the actual number of distinct attacking IPs.

---

## Known Limitations

**No concurrent write migration.** The import tool is a single-threaded sequential importer. It is not designed for live migration of a continuously-written JSONL file. The recommended procedure is to stop the application during import, then restart pointing at SQLite.

**JSONL watcher not in Phase 1.** The file-watcher that picks up new lines appended by sensors directly to the JSONL file is a Phase 2 concern. During Phase 1, all event writes must go through `POST /api/ingest`. Sensors that write directly to the JSONL file will need to be reconfigured to use the HTTP API, or the watcher must be implemented before sensors are updated.

---

*Cross-references: [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md)*
