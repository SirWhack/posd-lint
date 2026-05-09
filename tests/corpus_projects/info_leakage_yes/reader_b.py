from pkg.ticket import Ticket


def to_dict(t: Ticket):
    return {"id": t.id, "title": t.title, "project_name": t.project_name}
