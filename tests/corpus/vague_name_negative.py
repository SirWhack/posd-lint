"""Should NOT flag: precise domain names."""


def parse_time_entry(raw_entry: str) -> int:
    """Specific function with specific parameter."""
    duration_minutes = int(raw_entry.rstrip("m"))
    return duration_minutes


class TicketRepository:
    """Specific domain class."""

    def find_by_id(self, ticket_id: str) -> dict:
        """Specific method, specific param."""
        return {"id": ticket_id}


for i in range(10):
    pass  # i in tight loop is fine
