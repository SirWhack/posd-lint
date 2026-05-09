"""Should NOT flag: dispatch-named functions, single isinstance, dunders, singledispatch."""

from functools import singledispatch


def dispatch_event(event):
    """Dispatch is the contract — name signals it."""
    if isinstance(event, dict):
        return event["type"]
    if isinstance(event, str):
        return event
    return None


def parse_input(raw):
    """parse_* is a recognized dispatch name."""
    if isinstance(raw, bytes):
        return raw.decode()
    if isinstance(raw, str):
        return raw
    return ""


def take_string(x: str | None) -> str:
    """Single isinstance() for narrowing — under threshold."""
    if isinstance(x, str):
        return x
    return ""


@singledispatch
def render(obj):
    """Standard dispatch via decorator — not the smell."""
    if isinstance(obj, dict):
        return ""
    if isinstance(obj, list):
        return ""
    return str(obj)


class MyClass:
    def __eq__(self, other):
        # Dunders need isinstance for correctness — exempt.
        if not isinstance(other, MyClass):
            return False
        if not isinstance(other.x, int):
            return False
        return True
