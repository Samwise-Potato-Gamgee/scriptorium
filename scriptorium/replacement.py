# Replacing an edition's file safely: stage and verify the new copy,
# park the old files in the trash, swap, then update the database.
from __future__ import annotations

import shutil
from pathlib import Path

from . import db, naming, trash
from .importer import (
    ImportFailure,
    _apply,
    _delete_originals,
    _existing,
    _rollback,
    _stage,
    read_source,
)
from .library import Library


def _ensure_directory(path: Path, created: list[Path]) -> None:
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


def replace_edition(
    library: Library,
    edition_id: int,
    raw_path: str,
    edition_fields: dict | None = None,
    keep_original: bool = False,
) -> dict:
    edition_fields = edition_fields or {}
    source = _existing(raw_path)
    prepared = read_source(source)
    with db.session(library.db_path) as connection:
        edition = db.get_edition(connection, int(edition_id))
        book = (
            db.get_book(connection, edition["book_id"]) if edition is not None else None
        )
    if edition is None or book is None:
        raise ImportFailure("this edition no longer exists")
    if prepared["format"] != edition["kind"]:
        raise ImportFailure(
            "choose a file of the same format as the edition being replaced"
        )
    book_directory = library.path(book.get("folder") or "")
    if not book_directory.is_dir():
        raise ImportFailure("the book's folder is missing, so the file cannot be replaced")
    stage_directory = library.staging()
    state = {"moved": [], "cover_names": [], "created": []}
    parked = None
    try:
        staged = _stage(stage_directory, prepared)
        parked = trash.park_replaced(library, book, edition, source.name)
        stem = naming.sanitize(book["title"])
        audio_directory = None
        targets = []
        if edition["kind"] == "ebook":
            for item in prepared["files"]:
                targets.append(
                    naming.free_path(
                        book_directory, f"{stem}{item['path'].suffix.lower()}"
                    )
                )
        else:
            audio_directory = book_directory / "audio"
            _ensure_directory(audio_directory, state)
            if prepared["is_folder"]:
                width = naming.padding_width(len(prepared["files"]))
                for index, item in enumerate(prepared["files"]):
                    name = f"{index + 1:0{width}d} - {stem}{item['path'].suffix.lower()}"
                    targets.append(naming.free_path(audio_directory, name))
            else:
                for item in prepared["files"]:
                    targets.append(
                        naming.free_path(
                            audio_directory, f"{stem}{item['path'].suffix.lower()}"
                        )
                    )
        layout = {
            "folder": library.relative(book_directory),
            "folder_path": book_directory,
            "audio_path": audio_directory,
            "targets": targets,
        }
        _apply(layout, staged, state)
        files = []
        for position, entry in enumerate(staged):
            files.append(
                {
                    "path": library.relative(targets[position]),
                    "position": position,
                    "size": entry["size"],
                    "checksum": entry["checksum"],
                    "duration": float(entry["item"]["duration"] or 0),
                }
            )
        if edition["kind"] == "ebook":
            edition_path = files[0]["path"] if files else ""
            duration = 0.0
            is_folder = False
            narrator = ""
        else:
            is_folder = bool(prepared["is_folder"])
            edition_path = (
                library.relative(audio_directory)
                if is_folder
                else (files[0]["path"] if files else "")
            )
            duration = sum(float(entry["item"]["duration"] or 0) for entry in staged)
            narrator = (
                naming.collapse(edition_fields.get("narrator"))
                or edition.get("narrator")
                or prepared["metadata"].get("narrator")
                or ""
            )
        with db.session(library.db_path) as connection:
            db.update_edition(
                connection,
                int(edition_id),
                {
                    "is_folder": is_folder,
                    "path": edition_path,
                    "duration": duration,
                    "narrator": narrator,
                },
            )
            db.replace_edition_files(connection, int(edition_id), files)
    except BaseException:
        _rollback(library, state)
        if parked is not None:
            trash.unpark(parked)
        shutil.rmtree(stage_directory, ignore_errors=True)
        raise
    shutil.rmtree(stage_directory, ignore_errors=True)
    warnings = [] if keep_original else _delete_originals(library, prepared)
    return {"book_id": book["id"], "warnings": warnings}
