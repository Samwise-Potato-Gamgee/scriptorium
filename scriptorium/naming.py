# Windows-safe names for library folders and files: sanitising,
# shortening at word boundaries, reserved names and clash suffixes.
from __future__ import annotations

import os
import re
from pathlib import Path

FORBIDDEN_CHARACTERS = set('<>:"/\\|?*')
RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
LIBRARY_RESERVED = {
    "covers",
    "thumbnails",
    "backups",
    "trash",
    ".staging",
    "library.db",
}
MAX_LENGTH = 80


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def shorten(text: str, max_length: int = MAX_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    cut = text[:max_length]
    boundary = cut.rfind(" ")
    if boundary >= max_length // 3:
        cut = cut[:boundary]
    return cut.rstrip(" .")


def sanitize(name: str, max_length: int = MAX_LENGTH) -> str:
    characters = []
    for character in str(name or ""):
        if character in FORBIDDEN_CHARACTERS or ord(character) < 32:
            characters.append(" ")
        else:
            characters.append(character)
    cleaned = collapse("".join(characters)).rstrip(". ")
    cleaned = shorten(cleaned, max_length).rstrip(". ")
    if not cleaned:
        cleaned = "Untitled"
    if cleaned.casefold() in RESERVED_NAMES:
        cleaned = cleaned + "_"
    return cleaned


def author_folder(name: str) -> str:
    cleaned = sanitize(name) if str(name or "").strip() else "Unknown"
    if cleaned.casefold() in LIBRARY_RESERVED:
        cleaned = cleaned + " (author)"
    return cleaned


def taken_names(parent: Path) -> set[str]:
    try:
        return {entry.name.casefold() for entry in parent.iterdir()}
    except OSError:
        return set()


def unique_entry(parent: Path, base: str, ignore: str | None = None) -> str:
    names = taken_names(parent)
    if ignore is not None:
        names.discard(ignore.casefold())
    if base.casefold() not in names:
        return base
    number = 2
    while f"{base} ({number})".casefold() in names:
        number += 1
    return f"{base} ({number})"


def same_path(first: Path, second: Path) -> bool:
    left = os.path.normcase(os.path.abspath(str(first)))
    right = os.path.normcase(os.path.abspath(str(second)))
    return left == right


def free_path(directory: Path, name: str, current: Path | None = None) -> Path:
    candidate = directory / name
    if current is not None and same_path(candidate, current):
        return candidate
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    number = 2
    while True:
        attempt = directory / f"{stem} ({number}){suffix}"
        if not attempt.exists() or (current is not None and same_path(attempt, current)):
            return attempt
        number += 1


def author_sort_key(name: str) -> str:
    words = str(name or "").split()
    if not words:
        return ""
    return collapse(" ".join([words[-1], *words[:-1]])).casefold()


def last_first_to_first_last(name: str) -> str | None:
    if str(name or "").count(",") != 1:
        return None
    last, first = (part.strip() for part in str(name).split(","))
    if not last or not first:
        return None
    return f"{first} {last}"


def padding_width(count: int) -> int:
    return max(2, len(str(max(count, 1))))
