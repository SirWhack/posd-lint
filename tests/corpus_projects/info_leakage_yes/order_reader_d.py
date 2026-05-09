from pkg.order import OrderRepository


def first_id(repo: OrderRepository):
    o = repo.get_one()
    return o.id
