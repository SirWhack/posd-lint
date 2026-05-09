"""Should NOT flag: clear docstrings on public surfaces; trivial bodies skipped."""


class TimeReporter:
    """Generates daily and weekly time reports for a user."""

    def generate_report(self, user_id: str, start_date, end_date) -> dict:
        """Build a date-bounded report of the user's entries.

        Returns a dict keyed by category with totals in minutes.
        """
        entries = self._fetch(user_id)
        filtered = [e for e in entries if start_date <= e.date <= end_date]
        return self._format(filtered)

    def _fetch(self, user_id):
        return []

    def _format(self, entries):
        return {}


def x_squared(n: int) -> int:
    """Trivial — single-line body, exempt from docstring requirement anyway."""
    return n * n


def short_no_doc(n):
    return n + 1
