"""Should NOT flag: simple linear functions, all under threshold 10."""


def add(a, b):
    return a + b


def greet(name):
    if not name:
        return "hello"
    return f"hello {name}"


def total(items):
    sum_ = 0
    for item in items:
        sum_ += item
    return sum_
