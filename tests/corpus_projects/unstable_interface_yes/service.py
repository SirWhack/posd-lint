from typing import Protocol


class BigServiceProtocol(Protocol):
    def do_thing(self) -> int: ...


class BigService:
    def do_thing(self) -> int:
        return 1
