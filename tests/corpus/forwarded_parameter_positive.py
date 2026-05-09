"""Should flag: parameter only used to be forwarded."""


def post(url, payload, retries):
    """`retries` is forwarded once and not used otherwise."""
    response = http_call(url, payload)
    return enqueue_retry(response, retries)


def http_call(u, p):
    return {"u": u}


def enqueue_retry(r, n):
    return r
