"""Should flag: many params and many optional params."""


def upsert_ticket(
    ticket_id: str,
    title: str,
    project_name: str | None = None,
    ticket_number: str | None = None,
    company_name: str | None = None,
    description: str | None = None,
    issue_type: str | None = None,
    sub_issue_type: str | None = None,
    status: str = "active",
    user_id: str = "local-user",
):
    """13 parameters, 10 optional."""
    return ticket_id


class Job:
    def configure(self, a, b, c, d, e, f, g, h):
        """8 positional params."""
        return None
