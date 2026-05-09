"""Should flag: a variable reused for a different kind of value."""


def process(items):
    result = []  # list
    for item in items:
        result.append(item)
    result = {x: True for x in result}  # now a dict — repurpose
    return result


def collect(values):
    output = ""  # str
    for v in values:
        output += str(v)
    output = len(output)  # now an int — repurpose
    return output
