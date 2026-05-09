from pkg.order import OrderRepository


def total_all(repo: OrderRepository):
    s = 0
    for o in repo.list_orders():
        s += o.total
    return s
