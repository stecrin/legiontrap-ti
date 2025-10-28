# Lightweight file rotation & retention helpers for events.jsonl
# Why: keep storage bounded in containers and on small VPS.
# Notes: rotate on size; prune rotated files older than RETENTION_DAYS.
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path


def roll_files_if_needed(path: Path, max_bytes: int = 1_000_000) -> None:
    """Rotate path to path-<timestamp>.jsonl when size >= max_bytes; never raise."""
    try:
        if path.exists() and path.stat().st_size >= max_bytes:
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            rotated = path.with_name(f"{path.stem}-{ts}{path.suffix}")
            shutil.move(str(path), str(rotated))
            path.touch()
    except Exception:
        pass  # never crash API on rotation issues


def prune_old_files(path: Path, retention_days: int = 14) -> None:
    """Delete rotated files older than retention_days; ignore parse errors."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        parent = path.parent
        stem, suffix = path.stem, path.suffix
        for p in parent.glob(f"{stem}-*{suffix}"):
            name_ts = p.name.replace(f"{stem}-", "").replace(suffix, "")
            try:
                dt = datetime.strptime(name_ts, "%Y%m%d-%H%M%S")
                if dt < cutoff:
                    p.unlink(missing_ok=True)
            except Exception:
                continue
    except Exception:
        pass
