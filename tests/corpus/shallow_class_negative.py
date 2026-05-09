"""Should NOT flag: deep class, dataclass, exempt bases."""

from dataclasses import dataclass
from enum import Enum


@dataclass
class TimeEntry:
    """Dataclass — exempt by decorator."""
    user_id: str
    duration_minutes: int
    task: str


class Status(Enum):
    """Enum — exempt by base."""
    PENDING = "pending"
    SYNCED = "synced"


class TicketSyncService:
    """Substantive class — methods have real bodies."""

    def sync_all(self, user_id: str) -> int:
        pending = self._fetch_pending(user_id)
        results = []
        for entry in pending:
            try:
                response = self._post(entry)
                self._mark_synced(entry, response.id)
                results.append(True)
            except Exception:
                self._mark_failed(entry)
                results.append(False)
        return sum(results)

    def reset(self, user_id: str) -> None:
        all_entries = self._fetch_all(user_id)
        for entry in all_entries:
            entry.sync_status = "pending"
            self._save(entry)

    def _fetch_pending(self, user_id):
        return []

    def _fetch_all(self, user_id):
        return []

    def _post(self, entry):
        return type("R", (), {"id": "x"})()

    def _mark_synced(self, entry, ext_id):
        entry.external_id = ext_id

    def _mark_failed(self, entry):
        entry.failed = True

    def _save(self, entry):
        pass
