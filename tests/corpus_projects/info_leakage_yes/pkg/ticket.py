"""Ticket schema — leaked across many files."""


class Ticket:
    def __init__(self, ticket_id, title, project_name, ticket_number, status):
        self.id = ticket_id
        self.title = title
        self.project_name = project_name
        self.ticket_number = ticket_number
        self.status = status
