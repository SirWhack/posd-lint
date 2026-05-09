"""Should flag: public docstrings that talk about implementation."""


def get_user(user_id: str) -> dict:
    """Retrieve a user by id.

    Internally this uses a Redis cache with a 5-minute TTL.
    """
    return {"id": user_id}


class TicketStore:
    """Stores tickets.

    We use SQLite under the hood; the table is `tickets`.
    """

    def find(self, ticket_id: str) -> dict:
        """Look up a ticket. Currently returns the dict from self._cache."""
        return {"id": ticket_id}


def post_message(text: str) -> bool:
    """Send a message.

    TODO: handle rate limits properly.
    """
    return True
