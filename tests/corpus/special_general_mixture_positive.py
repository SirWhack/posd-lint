"""Should flag: 'general' function with type-specific branches."""


def process(item):
    """Generically named — but actually dispatches on type."""
    if isinstance(item, dict):
        return item.get("value")
    if isinstance(item, list):
        return item[0] if item else None
    if isinstance(item, str):
        return item.strip()
    return None


def summarize(value):
    """Two isinstance() checks — likely should be split."""
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    if isinstance(value, str):
        return value.upper()
    return ""
