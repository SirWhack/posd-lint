from leaf import leaf_fn


def middle_fn(name, payload, token):
    print("middle invoked for", name)
    return leaf_fn(name, payload, token)
