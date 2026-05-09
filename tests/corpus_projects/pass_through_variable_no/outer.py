from middle import middle_fn


def outer_fn(name, payload, token):
    return middle_fn(name, payload, token)
