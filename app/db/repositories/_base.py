"""
Shared base for all repository mixins.

Owns the session reference and the lazy-loaded event_types cache used by
write methods to coerce unknown event_type values to 'unknown'.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


class RepositoryBase:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._valid_event_types: frozenset[str] | None = None

    def _load_valid_event_types(self) -> frozenset[str]:
        """
        Load event_type IDs from the event_types lookup table.
        Called once per repository instance; result is cached.
        Keeps the coercion logic in sync with the actual DB state rather
        than a hardcoded list.
        """
        if self._valid_event_types is None:
            rows = self._session.execute(text("SELECT id FROM event_types")).fetchall()
            self._valid_event_types = frozenset(row[0] for row in rows)
        return self._valid_event_types
