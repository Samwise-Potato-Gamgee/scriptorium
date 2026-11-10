# Import pipeline: inspect a source path, stage and verify copies,
# write the database entry, and only then delete the originals.
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from . import covers, db, metadata, naming
from .library import Library
from .textutil import (
    clean_authors,
    clean_series_number,
    clean_status,
    clean_subgenres,
)

CHUNK_SIZE = 1024 * 1024


class ImportFailure(Exception):
    pass


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _copy(source: Path, target: Path) -> None:
    shutil.copy2(source, target)


def _move(source: Path, target: Path) -> None:
    os.replace(source, target)


def _existing(raw: str) -> Path:
    text = str(raw or "").strip()
    if not text:
        raise ImportFailure("a file or folder path is required")
    source = Path(text).expanduser()
    if not source.exists():
        raise ImportFailure(f"the path does not exist: {text}")
    return source


def read_source(source: Path) -> dict:
    try:
        if source.is_dir():
            metadata_result = metadata.read_audio_folder(source)
            files = [
                {
                    "path": entry["path"],
                    "duration": float(entry["duration"] or 0),
                    "track": entry["track"],
                }
                for entry in metadata_result["entries"]
            ]
            return {
                "source": source,
                "format": "audiobook",
                "is_folder": True,
                "metadata": metadata_result,
                "files": files,
                "original_name": source.name,
            }
        suffix = source.suffix.lower()
        if suffix in metadata.EBOOK_EXTENSIONS:
            metadata_result = metadata.read_epub(source)
            file_format = "ebook"
        elif suffix in metadata.AUDIO_EXTENSIONS:
            metadata_result = metadata.read_audio(source)
            file_format = "audiobook"
        else:
            raise ImportFailure(
                "unsupported file type; choose an EPUB, MP3, M4A or M4B file, or a folder of audio files"
            )
        return {
            "source": source,
            "format": file_format,
            "is_folder": False,
            "metadata": metadata_result,
            "files": [
                {
                    "path": source,
                    "duration": float(metadata_result.get("duration") or 0),
                    "track": metadata_result.get("track"),
                }
            ],
            "original_name": source.name,
        }
    except metadata.InvalidFile as error:
        raise ImportFailure(str(error))
    except OSError as error:
        raise ImportFailure(f"the source could not be read: {error}")


def inspect_source(library: Library | None, raw_path: str) -> dict:
    source = _existing(raw_path)
    prepared = read_source(source)
    found = prepared["metadata"]
    total_size = 0
    for item in prepared["files"]:
        try:
            total_size += item["path"].stat().st_size
        except OSError:
            pass
    duplicates = []
    if library is not None:
        first_author = (found.get("authors") or [""])[0]
        with db.session(library.db_path) as connection:
            duplicates = db.find_duplicates(
                connection, found.get("title") or "", first_author
            )
    return {
        "path": str(source),
        "source_kind": "folder" if prepared["is_folder"] else "file",
        "format": prepared["format"],
        "file_count": len(prepared["files"]),
        "total_size": total_size,
        "metadata": {
            "title": found.get("title") or "",
            "authors": found.get("authors") or [],
            "narrator": found.get("narrator") or "",
            "description": found.get("description") or "",
            "series": found.get("series") or "",
            "series_number": found.get("series_number") or "",
            "duration": float(found.get("duration") or 0),
        },
        "cover_preview": covers.preview_data_url(found.get("cover") or b""),
        "duplicates": [
            {
                "id": book["id"],
                "title": book["title"],
                "authors": book["authors"],
                "has_ebook": book["has_ebook"],
                "has_audiobook": book["has_audiobook"],
                "cover": book["cover"],
                "thumbnail": book["thumbnail"],
            }
            for book in duplicates
        ],
    }


def _ensure_directory(path: Path, state: dict) -> None:
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for directory in reversed(missing):
        try:
            directory.mkdir()
            state["created"].append(directory)
        except FileExistsError:
            continue


def _book_folder(library: Library, title: str, authors: list[str], state: dict) -> Path:
    author_name = authors[0] if authors else ""
    author_directory = library.root / naming.author_folder(author_name)
    _ensure_directory(author_directory, state)
    folder_name = naming.unique_entry(author_directory, naming.sanitize(title))
    book_directory = author_directory / folder_name
    _ensure_directory(book_directory, state)
    return book_directory


def _existing_folder(library: Library, book: dict, state: dict) -> Path:
    stored = book.get("folder") or ""
    if stored:
        folder = library.path(stored)
        _ensure_directory(folder, state)
        return folder
    folder = _book_folder(
        library, book.get("title") or "Untitled", book.get("authors") or [], state
    )
    return folder


def _targets(
    library: Library,
    prepared: dict,
    book_directory: Path,
    title: str,
    state: dict,
) -> dict:
    stem = naming.sanitize(title)
    folder_relative = library.relative(book_directory)
    audio_directory = None
    targets = []
    if prepared["format"] == "ebook":
        for item in prepared["files"]:
            extension = item["path"].suffix.lower() or ".epub"
            targets.append(naming.free_path(book_directory, f"{stem}{extension}"))
    else:
        audio_directory = book_directory / "audio"
        _ensure_directory(audio_directory, state)
        if prepared["is_folder"]:
            width = naming.padding_width(len(prepared["files"]))
            for index, item in enumerate(prepared["files"]):
                extension = item["path"].suffix.lower()
                name = f"{index + 1:0{width}d} - {stem}{extension}"
                targets.append(naming.free_path(audio_directory, name))
        else:
            for item in prepared["files"]:
                extension = item["path"].suffix.lower()
                targets.append(naming.free_path(audio_directory, f"{stem}{extension}"))
    return {
        "folder": folder_relative,
        "folder_path": book_directory,
        "audio_path": audio_directory,
        "targets": targets,
    }


def _stage(stage_directory: Path, prepared: dict) -> list[dict]:
    staged = []
    for index, item in enumerate(prepared["files"]):
        extension = item["path"].suffix.lower()
        target = stage_directory / f"{index:04d}{extension}"
        source_size = item["path"].stat().st_size
        source_checksum = _digest(item["path"])
        try:
            _copy(item["path"], target)
        except OSError as error:
            raise ImportFailure(f"the file could not be copied: {error}")
        try:
            copied_size = target.stat().st_size
            copied_checksum = _digest(target)
        except OSError as error:
            raise ImportFailure(f"the copied file could not be checked: {error}")
        if copied_size != source_size or copied_checksum != source_checksum:
            raise ImportFailure(
                "the copy could not be verified, so the original was left untouched"
            )
        staged.append(
            {
                "item": item,
                "staged": target,
                "size": copied_size,
                "checksum": copied_checksum,
            }
        )
    return staged


def _apply(layout: dict, staged: list[dict], state: dict) -> None:
    for entry, target in zip(staged, layout["targets"]):
        try:
            _move(entry["staged"], target)
        except OSError as error:
            raise ImportFailure(f"the file could not be moved into the library: {error}")
        state["moved"].append(target)


def _save_cover(library: Library, data: bytes, state: dict) -> tuple[str, str] | None:
    if not data:
        return None
    try:
        names = covers.save(library, data)
    except covers.CoverError:
        return None
    state["cover_names"].append(names[0])
    return names


def _edition(
    library: Library,
    prepared: dict,
    layout: dict,
    staged: list[dict],
    edition_fields: dict,
) -> dict:
    files = []
    for position, entry in enumerate(staged):
        files.append(
            {
                "path": library.relative(layout["targets"][position]),
                "position": position,
                "size": entry["size"],
                "checksum": entry["checksum"],
                "duration": float(entry["item"]["duration"] or 0),
            }
        )
    if prepared["format"] == "ebook":
        path = files[0]["path"] if files else ""
        duration = 0.0
        narrator = ""
        is_folder = False
    else:
        path = layout["folder"] + "/audio"
        if not prepared["is_folder"]:
            path = files[0]["path"] if files else ""
        duration = sum(entry["item"]["duration"] for entry in staged)
        narrator = str(edition_fields.get("narrator") or "").strip()
        if not narrator:
            narrator = prepared["metadata"].get("narrator") or ""
        is_folder = bool(prepared["is_folder"])
    return {
        "kind": prepared["format"],
        "is_folder": is_folder,
        "path": path,
        "duration": duration,
        "narrator": narrator,
        "cover": "",
        "thumbnail": "",
        "imported_from": prepared["original_name"],
        "imported_from_kind": "folder" if prepared["is_folder"] else "file",
        "files": files,
    }


def _book_fields(book_fields: dict, prepared: dict) -> tuple[dict, list, list]:
    found = prepared["metadata"]
    title = naming.collapse(book_fields.get("title")) or found.get("title") or ""
    if not title:
        raise ImportFailure("a title is required")
    if "authors" in book_fields:
        authors = clean_authors(book_fields.get("authors"))
    else:
        authors = clean_authors(found.get("authors") or [])
    description = str(book_fields.get("description", found.get("description") or "")).strip()
    series = naming.collapse(book_fields.get("series", found.get("series") or ""))
    series_number = clean_series_number(
        book_fields.get("series_number", found.get("series_number") or "")
    )
    genre = naming.collapse(book_fields.get("genre")) or "Other"
    subgenres = clean_subgenres(book_fields.get("subgenres") or [])
    needs_review = bool(book_fields.get("needs_review")) or not authors
    book = {
        "title": title,
        "description": description,
        "series": series,
        "series_number": series_number,
        "status": clean_status(book_fields.get("status")),
        "genre": genre,
        "needs_review": needs_review,
        "imported_from": prepared["original_name"],
        "imported_from_kind": "folder" if prepared["is_folder"] else "file",
        "folder": "",
        "cover": "",
        "thumbnail": "",
    }
    return book, authors, subgenres


def _rollback(library: Library, state: dict) -> None:
    for moved in reversed(state["moved"]):
        try:
            moved.unlink()
        except OSError:
            pass
    for name in state["cover_names"]:
        covers.remove(library, name)
    for directory in reversed(state["created"]):
        try:
            directory.rmdir()
        except OSError:
            pass


def _delete_originals(library: Library, prepared: dict) -> list[str]:
    warnings = []
    source = prepared["source"]
    try:
        inside_library = source.resolve().is_relative_to(library.root.resolve())
    except OSError:
        inside_library = False
    if inside_library:
        return ["the source is inside the library folder, so it was not deleted"]
    if prepared["is_folder"]:
        for item in prepared["files"]:
            try:
                item["path"].unlink()
            except OSError as error:
                warnings.append(
                    f"the original file '{item['path'].name}' could not be deleted: {error}"
                )
        try:
            source.rmdir()
        except OSError:
            pass
    else:
        try:
            source.unlink()
        except OSError as error:
            warnings.append(f"the original file could not be deleted: {error}")
    return warnings


def import_source(library: Library, payload: dict) -> dict:
    source = _existing(str(payload.get("path") or ""))
    prepared = read_source(source)
    requested_format = str(payload.get("format") or prepared["format"])
    if requested_format != prepared["format"]:
        raise ImportFailure("the selected format does not match the source")
    mode = str(payload.get("mode") or "new")
    keep_original = bool(payload.get("keep_original"))
    target_id = payload.get("target_book_id")
    book_fields = payload.get("book") or {}
    edition_fields = payload.get("edition") or {}
    stage_directory = library.staging()
    state = {"moved": [], "cover_names": [], "created": []}
    book_id = None
    try:
        staged = _stage(stage_directory, prepared)
        with db.session(library.db_path) as connection:
            target = None
            if mode == "attach":
                if not target_id:
                    raise ImportFailure("no book was chosen to attach to")
                target = db.get_book(connection, int(target_id))
                if target is None:
                    raise ImportFailure("the book to attach to no longer exists")
                if any(edition["kind"] == prepared["format"] for edition in target["editions"]):
                    raise ImportFailure("this book already has an edition of that format")
                book_directory = _existing_folder(library, target, state)
                layout = _targets(
                    library, prepared, book_directory, target["title"], state
                )
                edition = _edition(
                    library, prepared, layout, staged, edition_fields
                )
                cover_names = _save_cover(
                    library, prepared["metadata"].get("cover") or b"", state
                )
                if cover_names:
                    edition["cover"], edition["thumbnail"] = cover_names
                db.insert_edition(connection, target["id"], edition, edition["files"])
                db.update_book(connection, target["id"], {"folder": layout["folder"]})
                book_id = target["id"]
            else:
                book, authors, subgenres = _book_fields(book_fields, prepared)
                book_directory = _book_folder(library, book["title"], authors, state)
                layout = _targets(
                    library, prepared, book_directory, book["title"], state
                )
                edition = _edition(
                    library, prepared, layout, staged, edition_fields
                )
                cover_names = _save_cover(
                    library, prepared["metadata"].get("cover") or b"", state
                )
                if cover_names:
                    book["cover"], book["thumbnail"] = cover_names
                book["folder"] = layout["folder"]
                book_id = db.insert_book(connection, book, authors, subgenres)
                db.insert_edition(connection, book_id, edition, edition["files"])
            _apply(layout, staged, state)
    except BaseException:
        _rollback(library, state)
        shutil.rmtree(stage_directory, ignore_errors=True)
        raise
    shutil.rmtree(stage_directory, ignore_errors=True)
    warnings = [] if keep_original else _delete_originals(library, prepared)
    return {"book_id": book_id, "warnings": warnings}
