from pkg.ticket import Ticket


def is_open(t: Ticket):
    return t.status != "closed"
