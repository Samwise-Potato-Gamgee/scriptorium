# Editing books: field updates, safe folder and file renaming,
# bulk edits and cover replacement.
from __future__ import annotations

import os
from pathlib import Path

from . import covers, db, naming
from .library import Library
from .textutil import (
    clean_authors,
    clean_series_number,
    clean_status,
    clean_subgenres,
)


class EditFailure(Exception):
    pass


def _rename_path(source, target) -> None:
    source = Path(str(source))
    target = Path(str(target))
    if naming.same_path(source, target):
        return
    if source.parent == target.parent and source.name.casefold() == target.name.casefold():
        temporary = source.with_name(source.name + ".rename-tmp")
        os.replace(source, temporary)
        os.replace(temporary, target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)


def _replace_prefix(relative: str, old: str, new: str) -> str:
    if old and (relative == old or relative.startswith(old + "/")):
        return new + relative[len(old):]
    return relative


def _ensure_directory(path, created: list) -> None:
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir()
        created.append(directory)


def _rename_plan(
    library: Library, book: dict, title: str, authors: list[str]
) -> tuple[list[tuple], str, dict, list]:
    old_relative = book.get("folder") or ""
    if not old_relative:
        return [], old_relative, {}, []
    old_directory = library.path(old_relative)
    if not old_directory.is_dir():
        if book.get("editions"):
            raise EditFailure(
                "the book's folder is missing, so it cannot be renamed; run Check library first"
            )
        return [], old_relative, {}, []
    stem = naming.sanitize(title)
    operations: list[tuple] = []
    plans: dict[int, dict] = {}
    created: list = []
    for edition in book.get("editions") or []:
        files = edition.get("files") or []
        if not files:
            continue
        if edition["kind"] == "ebook":
            targets = []
            for item in files:
                source = library.path(item["path"])
                targets.append(
                    naming.free_path(
                        source.parent, f"{stem}{source.suffix.lower()}", source
                    )
                )
            audio_directory = None
        else:
            if edition["is_folder"]:
                audio_directory = library.path(edition["path"])
            else:
                audio_directory = library.path(files[0]["path"]).parent
            width = naming.padding_width(len(files))
            targets = []
            for index, item in enumerate(files):
                source = library.path(item["path"])
                if edition["is_folder"]:
                    name = f"{index + 1:0{width}d} - {stem}{source.suffix.lower()}"
                else:
                    name = f"{stem}{source.suffix.lower()}"
                targets.append(naming.free_path(audio_directory, name, source))
        for item, target in zip(files, targets):
            source = library.path(item["path"])
            if not naming.same_path(source, target):
                operations.append((source, target))
        new_files = [
            {**item, "path": library.relative(target)}
            for item, target in zip(files, targets)
        ]
        if edition["kind"] == "ebook":
            new_path = new_files[0]["path"]
        elif edition["is_folder"]:
            new_path = library.relative(audio_directory)
        else:
            new_path = new_files[0]["path"]
        plans[edition["id"]] = {"path": new_path, "files": new_files}
    desired_author = library.root / naming.author_folder(
        authors[0] if authors else ""
    )
    desired_folder = desired_author / stem
    if naming.same_path(desired_folder, old_directory):
        final_directory = old_directory
    else:
        _ensure_directory(desired_author, created)
        ignore = (
            old_directory.name
            if naming.same_path(desired_author, old_directory.parent)
            else None
        )
        folder_name = naming.unique_entry(desired_author, stem, ignore)
        final_directory = desired_author / folder_name
        if not naming.same_path(final_directory, old_directory):
            operations.append((old_directory, final_directory))
    final_relative = library.relative(final_directory)
    if final_relative != old_relative:
        for plan in plans.values():
            plan["path"] = _replace_prefix(
                plan["path"], old_relative, final_relative
            )
            for item in plan["files"]:
                item["path"] = _replace_prefix(
                    item["path"], old_relative, final_relative
                )
    return operations, final_relative, plans, created


def update_book(
    library: Library,
    book_id: int,
    fields: dict,
    authors: list[str] | None = None,
    subgenres: list[str] | None = None,
) -> dict:
    executed: list[tuple] = []
    created: list = []
    try:
        with db.session(library.db_path) as connection:
            book = db.get_book(connection, book_id)
            if book is None:
                raise EditFailure("this book no longer exists")
            title = naming.collapse(fields.get("title", book["title"]))
            if not title:
                raise EditFailure("a title is required")
            new_authors = (
                clean_authors(authors) if authors is not None else book["authors"]
            )
            new_subgenres = (
                clean_subgenres(subgenres)
                if subgenres is not None
                else book["subgenres"]
            )
            updates = {"title": title}
            if "description" in fields:
                updates["description"] = str(fields.get("description") or "").strip()
            if "series" in fields:
                updates["series"] = naming.collapse(fields.get("series"))
            if "series_number" in fields:
                updates["series_number"] = clean_series_number(
                    fields.get("series_number")
                )
            if "status" in fields:
                updates["status"] = clean_status(fields.get("status"), book["status"])
            if "genre" in fields:
                updates["genre"] = (
                    naming.collapse(fields.get("genre")) or book["genre"]
                )
            if "needs_review" in fields:
                updates["needs_review"] = bool(fields.get("needs_review"))
            operations, folder, plans, created = [], book.get("folder") or "", {}, []
            if title != book["title"] or new_authors != book["authors"]:
                operations, folder, plans, created = _rename_plan(
                    library, book, title, new_authors
                )
            updates["folder"] = folder
            for source, target in operations:
                _rename_path(source, target)
                executed.append((source, target))
            db.update_book(connection, book_id, updates)
            db.replace_authors(connection, book_id, new_authors)
            db.replace_subgenres(connection, book_id, new_subgenres)
            for edition_id, plan in plans.items():
                db.update_edition(connection, edition_id, {"path": plan["path"]})
                db.replace_edition_files(connection, edition_id, plan["files"])
    except BaseException:
        for source, target in reversed(executed):
            try:
                _rename_path(target, source)
            except OSError:
                pass
        for directory in reversed(created):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    with db.session(library.db_path) as connection:
        result = db.get_book(connection, book_id)
    if result is None:
        raise EditFailure("this book no longer exists")
    return result


def update_edition_metadata(library: Library, edition_id: int, fields: dict) -> dict:
    with db.session(library.db_path) as connection:
        edition = db.get_edition(connection, int(edition_id))
        if edition is None:
            raise EditFailure("this edition no longer exists")
        if "narrator" in fields:
            db.update_edition(
                connection,
                int(edition_id),
                {"narrator": naming.collapse(fields.get("narrator"))},
            )
        book = db.get_book(connection, edition["book_id"])
    if book is None:
        raise EditFailure("this book no longer exists")
    return book


def bulk_update(library: Library, book_ids: list[int], fields: dict) -> int:
    updated = 0
    with db.session(library.db_path) as connection:
        for book_id in book_ids:
            book = db.get_book(connection, int(book_id))
            if book is None:
                continue
            updates = {}
            if naming.collapse(fields.get("genre")) and "genre" in fields:
                updates["genre"] = naming.collapse(fields.get("genre"))
            if "status" in fields and fields.get("status"):
                updates["status"] = clean_status(fields.get("status"), book["status"])
            if "series" in fields:
                updates["series"] = naming.collapse(fields.get("series"))
            if updates:
                db.update_book(connection, book_id, updates)
            if "subgenres" in fields:
                db.replace_subgenres(
                    connection, book_id, clean_subgenres(fields.get("subgenres"))
                )
            updated += 1
    return updated


def set_cover(
    library: Library, book_id: int, image: bytes, edition_id: int | None = None
) -> dict:
    try:
        saved = covers.save(library, image)
    except covers.CoverError as error:
        raise EditFailure(str(error))
    previous = ""
    try:
        with db.session(library.db_path) as connection:
            if edition_id is not None:
                edition = db.get_edition(connection, int(edition_id))
                if edition is None or edition["book_id"] != book_id:
                    raise EditFailure("this edition no longer exists")
                previous = edition.get("cover") or ""
                db.update_edition(
                    connection,
                    int(edition_id),
                    {"cover": saved[0], "thumbnail": saved[1]},
                )
            else:
                book = db.get_book(connection, book_id)
                if book is None:
                    raise EditFailure("this book no longer exists")
                previous = book.get("cover") or ""
                db.update_book(
                    connection,
                    book_id,
                    {"cover": saved[0], "thumbnail": saved[1]},
                )
    except BaseException:
        covers.remove(library, saved[0])
        raise
    if previous and previous != saved[0]:
        covers.remove(library, previous)
    return {"cover": saved[0], "thumbnail": saved[1]}
