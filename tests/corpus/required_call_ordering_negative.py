"""Should NOT flag: context-managed, dataclass, no pair, mismatched suffix."""

from dataclasses import dataclass


class Connection:
    """Has __enter__/__exit__ — protocol enforces ordering."""

    def open(self):
        self.connected = True

    def close(self):
        self.connected = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *a):
        self.close()


@dataclass
class Config:
    """Dataclass — exempt."""
    start: str = ""
    stop: str = ""


class Mixed:
    """start_session and close_window — different X — no pair."""

    def start_session(self):
        pass

    def close_window(self):
        pass
