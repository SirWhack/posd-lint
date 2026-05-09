"""Should NOT flag: contract-only docstrings; private symbols; dunders."""


def get_user(user_id: str) -> dict:
    """Return the user record matching user_id, or {} if no such user exists.

    The lookup is case-sensitive. Raises ValueError if user_id is empty.
    """
    return {"id": user_id}


class TicketStore:
    """A repository of tickets keyed by ticket id.

    Operations are atomic per ticket; concurrent reads are safe.
    """

    def find(self, ticket_id: str) -> dict:
        """Return the ticket with the given id, or {} if not found.

        Raises KeyError if ticket_id is None.
        """
        return {"id": ticket_id}


def _internal_helper():
    """We use a custom hash here. TODO: profile this."""
    # Private — implementation talk is appropriate.
    return None
