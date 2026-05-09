"""Should NOT flag: every param is used non-trivially (read 2+ times)."""


def post(url, payload, retries):
    """All three params read in a precondition AND in the call — not pass-through."""
    if not url.startswith("http"):
        raise ValueError(f"bad url: {url}")
    if not isinstance(payload, dict):
        raise TypeError(f"bad payload: {payload}")
    if retries <= 0:
        return None
    return http_call(url, payload, retries)


def double(value):
    """Two-param function — under MIN_PARAMS threshold; ignored regardless."""
    return value * 2


def http_call(u, p, n):
    return {"u": u, "p": p, "n": n}
