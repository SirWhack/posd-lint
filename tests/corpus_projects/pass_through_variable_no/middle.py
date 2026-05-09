from leaf import leaf_fn


def middle_fn(name, payload, token):
    if not payload:
        raise ValueError("payload required")
    if token.startswith("bearer "):
        token = token[len("bearer "):]
    return leaf_fn(name.lower(), payload, token)
