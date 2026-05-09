"""Order schema — leaked across many files via inferred receiver types."""


class Order:
    def __init__(self, order_id, total, currency, customer, status):
        self.id = order_id
        self.total = total
        self.currency = currency
        self.customer = customer
        self.status = status


class OrderRepository:
    def list_orders(self) -> list[Order]:
        return []

    def get_one(self) -> Order:
        return Order(0, 0, "USD", "", "")


def fetch_order() -> Order:
    return Order(0, 0, "USD", "", "")
