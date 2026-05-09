"""Should flag: missing or stub docstrings on public surfaces."""


class TimeReporter:
    def generate_report(self, user_id, start_date, end_date):
        entries = self._fetch(user_id)
        filtered = [e for e in entries if start_date <= e.date <= end_date]
        return self._format(filtered)

    def _fetch(self, user_id):
        return []

    def _format(self, entries):
        return str(entries)


def calculate_overtime(weekly_hours, threshold):
    excess = weekly_hours - threshold
    return excess if excess > 0 else 0


class SyncStatus:
    """Bad."""

    def sync(self, payload):
        result = self._send(payload)
        if result.ok:
            return True
        return False

    def _send(self, payload):
        return type("R", (), {"ok": True})()
