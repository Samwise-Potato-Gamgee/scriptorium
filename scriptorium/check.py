# Library consistency check: reports differences between database
# records and files on disk without changing anything.
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from . import db
from .library import Library

SKIPPED_TOP_LEVEL = {"backups", "trash", ".staging"}
CHUNK = 1024 * 1024


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _posix(relative: Path) -> str:
    text = relative.as_posix()
    return "" if text == "." else text


def check_library(library: Library) -> dict:
    problems = []
    known: set[str] = set()
    checked_files = 0
    with db.session(library.db_path) as connection:
        books = [
            db.get_book(connection, row["id"])
            for row in connection.execute("SELECT id FROM books ORDER BY id")
        ]
    for book in books:
        if book is None:
            continue
        title = book.get("title") or "Untitled"
        folder = book.get("folder") or ""
        if folder and book.get("editions"):
            folder_path = library.root.joinpath(*Path(folder).parts)
            if not folder_path.is_dir():
                problems.append(
                    {
                        "type": "missing_folder",
                        "message": f"the folder for '{title}' is missing",
                        "path": folder,
                        "book_id": book["id"],
                        "title": title,
                    }
                )
        for cover_key, kind in (("cover", "covers"), ("thumbnail", "thumbnails")):
            name = book.get(cover_key) or ""
            if name:
                relative = f"{kind}/{name}"
                known.add(relative)
                if not (library.root / kind / name).is_file():
                    problems.append(
                        {
                            "type": "missing_cover",
                            "message": f"a cover file for '{title}' is missing",
                            "path": relative,
                            "book_id": book["id"],
                            "title": title,
                        }
                    )
        for edition in book.get("editions") or []:
            for cover_key, kind in (("cover", "covers"), ("thumbnail", "thumbnails")):
                name = edition.get(cover_key) or ""
                if name:
                    relative = f"{kind}/{name}"
                    known.add(relative)
                    if not (library.root / kind / name).is_file():
                        problems.append(
                            {
                                "type": "missing_cover",
                                "message": f"an edition cover for '{title}' is missing",
                                "path": relative,
                                "book_id": book["id"],
                                "title": title,
                            }
                        )
            if edition.get("is_folder") and edition.get("path"):
                folder_path = library.root.joinpath(*Path(edition["path"]).parts)
                if not folder_path.is_dir():
                    problems.append(
                        {
                            "type": "missing_folder",
                            "message": f"the audio folder for '{title}' is missing",
                            "path": edition["path"],
                            "book_id": book["id"],
                            "title": title,
                        }
                    )
            for item in edition.get("files") or []:
                relative = item.get("path") or ""
                if not relative:
                    continue
                known.add(relative)
                checked_files += 1
                path = library.root.joinpath(*Path(relative).parts)
                if not path.is_file():
                    problems.append(
                        {
                            "type": "missing_file",
                            "message": f"a file for '{title}' is missing",
                            "path": relative,
                            "book_id": book["id"],
                            "title": title,
                        }
                    )
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    size = -1
                if int(item.get("size") or 0) != size:
                    problems.append(
                        {
                            "type": "size_mismatch",
                            "message": f"a file for '{title}' has a different size",
                            "path": relative,
                            "book_id": book["id"],
                            "title": title,
                        }
                    )
                    continue
                checksum = item.get("checksum") or ""
                if checksum:
                    try:
                        actual = _digest(path)
                    except OSError:
                        actual = ""
                    if actual and actual != checksum:
                        problems.append(
                            {
                                "type": "checksum_mismatch",
                                "message": f"a file for '{title}' has changed",
                                "path": relative,
                                "book_id": book["id"],
                                "title": title,
                            }
                        )
    known.add("library.db")
    for root, directories, files in os.walk(library.root):
        relative_root = Path(root).relative_to(library.root)
        if _posix(relative_root) == "":
            directories[:] = [name for name in directories if name not in SKIPPED_TOP_LEVEL]
        for name in files:
            relative = _posix(relative_root / name)
            if relative in known:
                continue
            problems.append(
                {
                    "type": "extra_file",
                    "message": "this file is not tracked by the library",
                    "path": relative,
                    "book_id": None,
                    "title": "",
                }
            )
    counts = {
        "missing": sum(
            1
            for problem in problems
            if problem["type"] in {"missing_file", "missing_folder", "missing_cover"}
        ),
        "changed": sum(
            1
            for problem in problems
            if problem["type"] in {"size_mismatch", "checksum_mismatch"}
        ),
        "extra": sum(1 for problem in problems if problem["type"] == "extra_file"),
    }
    return {
        "problems": problems,
        "counts": counts,
        "checked_books": len(books),
        "checked_files": checked_files,
    }
