# LegionTrap TI — JSONL Retirement and DB Snapshot Recovery Plan

**Document type:** Operational retirement plan
**Audience:** Engineers, operators, autonomous agents
**Last reviewed:** 2026-05-25
**Status:** Complete — JSONL write removed in Phase 3 PR 4; `scripts/import_jsonl.py` retained for operators with pre-existing JSONL data

---

## 1. Current JSONL Role

### What writes JSONL

`_append_jsonl()` in `app/routers/ingest.py` — the sole writer. Called after every successful DB
commit at Stage 6 of the ingest pipeline. It is best-effort: any I/O error is silently swallowed.
The JSONL write never blocks or fails an ingest.

### What reads JSONL

| Consumer | How it reads | Runtime dependency? |
|---|---|---|
| `scripts/import_jsonl.py` | Historical recovery tool — reads JSONL and replays into SQLite | No — operator-invoked only |
| `tests/unit/test_import_jsonl.py` | Tests for the import script; uses `tmp_path`, never the live file | No |
| `tests/test_privacy_and_auth.py` | Writes `storage/events.jsonl` directly for IOC-export testing | No — independent of `_append_jsonl()` |
| `app/core/config.py` | `EVENTS_FILE` setting — consumed only by `_append_jsonl()` | Yes, but only for the write path |

No production read path touches `events.jsonl`. All API responses, dashboard queries, IOC exports,
and intelligence endpoints read from SQLite only.

### Why it exists

JSONL was the primary event store before Phase 1 (SQLite migration). After Phase 1,
`_append_jsonl()` was retained as a write-through replica to preserve a disaster-recovery
guarantee documented in `MIGRATION_GUIDE.md`:

> *If the SQLite database is lost or corrupted, it can be fully reconstructed by re-importing
> the JSONL file.*

### Why it is now legacy

That guarantee no longer holds as written, for four reasons:

1. **Re-import does not reconstruct enrichment.** The JSONL file stores `HoneypotEvent`-level
   data — normalized events with `src_ip` extracted but no GeoIP, ASN, computed tags, or
   reputation scores. A re-import produces structurally correct but fully unenriched rows.
   Source IP reputation scores, geo data, and ASN records are lost permanently.

2. **The write is not atomic with the DB commit.** `_append_jsonl()` executes after
   `sp.commit()` as a non-transactional file append. Events committed to SQLite during a
   crash between the DB write and the file append are missing from JSONL. The file is not
   a guaranteed replica — it is a best-effort one.

3. **File size grows unboundedly.** No rotation, compression, or retention policy exists.
   `scripts/import_jsonl.py` has no mechanism to handle truncated or rotated files.

4. **`scripts/import_jsonl.py` is historical migration tooling.** It was written to migrate
   data from the JSONL-primary era into SQLite. It calls `upsert_source_ip()` without geo or
   ASN data, so even a clean re-import produces incomplete `source_ips` rows.

The JSONL file is a legacy artifact. It is not a reliable recovery mechanism for a system
that now includes enrichment, scoring, and intelligence indexes.

---

## 2. Replacement Recovery Strategy — SQLite DB Snapshots

### Backup approach

SQLite is a single file. The authoritative backup mechanism is a periodic file copy of
`storage/legiontrap.db`.

**Recommended: SQLite Online Backup API via `sqlite3` CLI**

```bash
# Consistent point-in-time backup — safe while the DB is open and writing
sqlite3 storage/legiontrap.db \
    ".backup storage/backups/legiontrap-$(date +%Y%m%d-%H%M%S).db"
```

The `.backup` command uses SQLite's Online Backup API, which produces a consistent snapshot
even under concurrent writes. The application does not need to stop.

**Alternative: file copy during a maintenance window**

```bash
cp storage/legiontrap.db \
   storage/backups/legiontrap-$(date +%Y%m%d-%H%M%S).db
```

Safe only when the application is not writing. Sufficient for edge deployments with scheduled
downtime windows.

### Backup location

```
storage/backups/
    legiontrap-20260525-020000.db
    legiontrap-20260524-020000.db
    ...
```

`storage/backups/` is covered by the `storage/*.db` gitignore rule. For production deployments,
replicate to off-host storage (S3, SFTP, NAS) immediately after creation.

### Retention expectations

| Deployment type | Suggested retention |
|---|---|
| Edge sensor (personal) | 7 daily backups |
| Lab / research | 14 daily + 4 weekly |
| Production TI feed | 30 daily + 12 weekly + 12 monthly |

Rotation is not implemented by LegionTrap. Use cron, a backup agent, or a shell script.

### Example cron schedule

```cron
# Daily backup at 02:00, retain 7 days
0 2 * * * cd /opt/legiontrap && \
    sqlite3 storage/legiontrap.db \
    ".backup storage/backups/legiontrap-$(date +\%Y\%m\%d-\%H\%M\%S).db" && \
    find storage/backups -name "*.db" -mtime +7 -delete
```

### Restore process

```bash
# 1. Stop the application
systemctl stop legiontrap   # or: kill the uvicorn process

# 2. Verify the backup is not corrupt
sqlite3 storage/backups/legiontrap-YYYYMMDD-HHMMSS.db "PRAGMA integrity_check;"
# Expected output: ok

# 3. Replace the active database
cp storage/legiontrap.db storage/legiontrap.db.bak   # optional safety copy
cp storage/backups/legiontrap-YYYYMMDD-HHMMSS.db storage/legiontrap.db

# 4. Start the application
systemctl start legiontrap

# 5. Validate (see below)
```

### Validation after restore

```bash
# Row counts — compare against last known-good values
sqlite3 storage/legiontrap.db "SELECT COUNT(*) FROM events;"
sqlite3 storage/legiontrap.db "SELECT COUNT(*) FROM raw_events;"
sqlite3 storage/legiontrap.db "SELECT COUNT(*) FROM source_ips;"

# Structural integrity
sqlite3 storage/legiontrap.db "PRAGMA integrity_check;"
# Expected: ok

# Alembic schema version matches current head
alembic current
# Expected: <head revision> (head)

# API smoke test
curl -s -H "x-api-key: $API_KEY" http://localhost:8088/api/stats | python -m json.tool
curl -s -H "x-api-key: $API_KEY" http://localhost:8088/api/intelligence/ips | python -m json.tool
```

**Expected data loss:** Events ingested between the backup timestamp and the failure are lost.
This is the accepted trade-off for a single-file SQLite deployment without WAL archiving or
streaming replication. For near-zero RPO requirements, schedule more frequent backups.

---

## 3. Phase 3 PR 4 Removal — Completed

### Code changes completed

| File | Change |
|---|---|
| `app/routers/ingest.py` | Removed `_append_jsonl()` function, Stage 6 call, and `from pathlib import Path` |
| `app/core/config.py` | Removed `EVENTS_FILE` setting |
| `.env.example` | Removed `EVENTS_FILE` line |

### Documentation changes completed

| Document | Change |
|---|---|
| `docs/ARCHITECTURE.md` | Removed `events.jsonl` from storage map and event flow; updated Storage Evolution Plan |
| `docs/INGESTION_PIPELINE.md` | Removed JSONL from Stage 5/6 flow diagram and section prose; updated overview step 6 |
| `docs/AUTONOMOUS_OPERATIONS.md` | Updated event store section to reflect write removal |
| `README.md` | Removed `events.jsonl` from architecture diagram; removed `EVENTS_FILE` env var row |

### Test changes completed

| File | Change |
|---|---|
| `tests/test_privacy_and_auth.py` | Removed dead JSONL write; added comment that the test exercises the SQLite-empty fallback path |

### What was NOT removed

`scripts/import_jsonl.py` and `tests/unit/test_import_jsonl.py` are **retained**. Operators who
have pre-existing `storage/events.jsonl` files from before this PR may still need to replay them
into SQLite. The import script remains available as an operator tool until operators confirm no
historical JSONL data remains unimported.

---

## 4. Status Summary

| Component | Current status |
|---|---|
| `_append_jsonl()` write | **Removed in Phase 3 PR 4** |
| `scripts/import_jsonl.py` | Retained — operator tool for replaying pre-existing JSONL into SQLite |
| `EVENTS_FILE` config setting | **Removed in Phase 3 PR 4** |
| `events.jsonl` as disaster-recovery source of truth | **Superseded** — SQLite DB snapshot is the replacement strategy (this document) |
| JSONL as primary event store | Retired in Phase 1 |

---

*Cross-references: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [INGESTION_PIPELINE.md](INGESTION_PIPELINE.md)*
