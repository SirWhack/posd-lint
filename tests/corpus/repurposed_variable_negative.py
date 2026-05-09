"""Should NOT flag: same kind preserved, None-init pattern, augmented assign."""


def process(items):
    result = []  # list
    for item in items:
        result.append(item)
    result = list(reversed(result))  # still a list — fine
    return result


def fetch():
    cache = None  # None-init: skipped
    cache = {"key": "value"}  # now a dict — but None→dict is the legitimate pattern
    return cache


def accumulate(values):
    total = 0  # int
    for v in values:
        total += v  # augmented assign — same kind
    return total
