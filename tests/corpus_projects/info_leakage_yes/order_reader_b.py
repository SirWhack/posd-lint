from pkg.order import OrderRepository


def show_currencies(repo: OrderRepository):
    out = []
    for o in repo.list_orders():
        out.append(o.currency)
    return out
