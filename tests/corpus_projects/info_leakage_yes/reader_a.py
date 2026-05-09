from pkg.ticket import Ticket


def show(t: Ticket):
    return f"{t.id} {t.title}"
