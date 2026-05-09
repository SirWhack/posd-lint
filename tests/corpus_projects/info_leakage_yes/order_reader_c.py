from pkg.order import fetch_order


def describe():
    o = fetch_order()
    return f"{o.customer}: {o.status}"
