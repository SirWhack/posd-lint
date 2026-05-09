"""Should flag: two functions with identical AST shape modulo local names."""


def compute_a(x):
    t = x * 2
    r = t + 1
    s = r - 3
    return s


def compute_b(y):
    m = y * 2
    n = m + 1
    o = n - 3
    return o
