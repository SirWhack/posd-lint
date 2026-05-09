"""Should flag: a function with ≥10 branching constructs."""


def classify(x, items, mode):
    total = 0
    if x > 0 and mode == "a":
        total += 1
    elif x < 0 or mode == "b":
        total -= 1
    for item in items:
        if item is None:
            continue
        if isinstance(item, int) and item > 10:
            total += item
        elif isinstance(item, str):
            total += len(item)
    while total > 100:
        total -= 1
    try:
        assert total >= 0
        return total
    except AssertionError:
        return 0
    except ValueError:
        return -1
