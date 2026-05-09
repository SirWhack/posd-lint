"""Examples of promised-pure functions with effects."""

from __future__ import annotations

import requests


def calculate_total(items):
    print("debug:", items)
    return sum(items)


def parse_user(raw):
    response = requests.get(f"https://example.com/users/{raw}")
    return response


def format_record(record):
    _persist_record(record)
    return str(record)


def _persist_record(record):
    with open("/tmp/log.txt", "a") as fh:
        fh.write(str(record))
