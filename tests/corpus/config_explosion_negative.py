"""Should NOT flag: reasonable parameter counts."""


def create_entry(user_id: str, duration_minutes: int, description: str) -> dict:
    """Three params; well under threshold."""
    return {"user_id": user_id, "duration": duration_minutes, "description": description}


class Service:
    def run(self, payload, retries: int = 3, timeout: float = 30.0):
        """Three params total — fine."""
        return payload
