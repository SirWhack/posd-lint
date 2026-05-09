"""Should NOT flag: same shape, different operators — distinct signatures."""


def add_chain(x):
    t = x + 2
    r = t + 1
    s = r + 3
    return s


def mul_chain(y):
    m = y * 2
    n = m * 1
    o = n * 3
    return o


def small(z):
    return z + 1
