# Shared normalisation helpers for book fields, authors, subgenres,
# statuses and series numbers.
from __future__ import annotations

from .naming import collapse

STATUS_VALUES = ("unread", "read", "didnt_finish")
STATUS_LABELS = {
    "unread": "Unread",
    "read": "Read",
    "didnt_finish": "Didn't finish",
}


def clean_text(value) -> str:
    return collapse(value)


def clean_authors(values) -> list[str]:
    if isinstance(values, str):
        values = values.split(",")
    result = []
    seen = set()
    for value in values or []:
        name = collapse(value)
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def clean_subgenres(values) -> list[str]:
    if isinstance(values, str):
        values = values.split(",")
    result = []
    seen = set()
    for value in values or []:
        name = collapse(value)
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def clean_series_number(value) -> str:
    text = collapse(value)
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number == int(number):
        return str(int(number))
    return str(number).rstrip("0").rstrip(".")


def clean_status(value, default: str = "unread") -> str:
    status = collapse(value)
    return status if status in STATUS_VALUES else default
