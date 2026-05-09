"""Should flag: a private helper called only by one public method."""


class Reporter:
    def generate(self, user_id):
        rows = self._fetch_and_format(user_id)
        return "\n".join(rows)

    def _fetch_and_format(self, user_id):
        # Non-trivial private helper, only called by `generate`.
        entries = [{"id": 1}, {"id": 2}]
        rows = []
        for e in entries:
            rows.append(f"{user_id}: {e['id']}")
        return rows
