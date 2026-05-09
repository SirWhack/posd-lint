"""Should NOT flag: shared private helpers, trivial helpers, or no entanglement."""


class Reporter:
    def generate_daily(self, user_id):
        return self._format(self._fetch(user_id))

    def generate_weekly(self, user_id):
        # _fetch and _format have multiple callers — they're shared helpers, not entangled.
        return self._format(self._fetch(user_id))

    def _fetch(self, user_id):
        entries = []
        for x in range(3):
            entries.append({"id": x})
        return entries

    def _format(self, entries):
        rows = []
        for e in entries:
            rows.append(str(e))
        return rows


class TrivialHelper:
    def public(self, x):
        return self._double(x)

    def _double(self, x):
        # Trivial: 1 statement, below threshold; not flagged.
        return x * 2
