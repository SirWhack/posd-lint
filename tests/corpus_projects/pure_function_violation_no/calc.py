"""Pure functions whose names promise purity and which deliver."""

from __future__ import annotations


def calculate_total(items):
    return sum(items)


def parse_user(raw):
    name, sep, rest = raw.partition(":")
    return {"name": name, "rest": rest}


def format_record(record):
    return f"<{record}>"


def to_dict(obj):
    return dict(obj)


def normalize_text(text):
    return text.strip().lower()
