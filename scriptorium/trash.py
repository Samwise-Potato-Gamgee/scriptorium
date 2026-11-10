# Trash operations: parking books, editions and replaced files with a
# manifest, listing, restoring and emptying the trash.
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from . import db, naming
from .library import Library


class TrashError(Exception):
    pass


def _tree_size(path: Path) -> int:
    total = 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for root, _directories, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


def _move(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)


def _move_back(moves: list[tuple[Path, Path]]) -> None:
    for current, original in reversed(moves):
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(current, original)
        except OSError:
            pass


def _ensure(path: Path, created: list[Path]) -> None:
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
            created.append(directory)
        except FileExistsError:
            continue


def _write_manifest(entry_directory: Path, manifest: dict) -> None:
    (entry_directory / "entry.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_manifest(entry_directory: Path) -> dict | None:
    try:
        data = json.loads((entry_directory / "entry.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _entry_directory(library: Library, entry_id: str) -> Path:
    if not entry_id or Path(entry_id).name != entry_id:
        raise TrashError("invalid trash entry")
    return library.trash_path(entry_id)


def _clean_empty(library: Library, relative: str) -> None:
    if not relative:
        return
    try:
        current = library.path(relative)
    except Exception:
        return
    for path in (current, current.parent):
        if path == library.root:
            break
        try:
            path.rmdir()
        except OSError:
            break


def _cover_names(book: dict, editions: list[dict]) -> set[str]:
    names = set()
    for item in [book, *editions]:
        if item.get("cover"):
            names.add(item["cover"])
        if item.get("thumbnail"):
            names.add(item["thumbnail"])
    return names


def trash_book(library: Library, book: dict) -> str:
    entry_id = uuid.uuid4().hex
    temporary = library.trash_path(f".tmp-{entry_id}")
    files_root = temporary / "files"
    files_root.mkdir(parents=True)
    final = library.trash_path(entry_id)
    moves: list[tuple[Path, Path]] = []
    folder_relative = book.get("folder") or ""
    try:
        if folder_relative:
            source = library.path(folder_relative)
            if source.exists():
                target = files_root / folder_relative
                _move(source, target)
                moves.append((target, source))
        covers = []
        for name in _cover_names(book, book.get("editions") or []):
            for kind in ("covers", "thumbnails"):
                source = library.root / kind / name
                if source.is_file():
                    target = files_root / kind / name
                    _move(source, target)
                    moves.append((target, source))
                    covers.append({"kind": kind, "name": name})
        manifest = {
            "id": entry_id,
            "kind": "book",
            "deleted_at": db.now_iso(),
            "title": book.get("title") or "Untitled",
            "authors": book.get("authors") or [],
            "folder": folder_relative,
            "book": book,
            "covers": covers,
            "size": _tree_size(files_root),
        }
        _write_manifest(temporary, manifest)
        os.replace(temporary, final)
        moves = [
            (final / current.relative_to(temporary), original)
            for current, original in moves
        ]
        with db.session(library.db_path) as connection:
            db.delete_book(connection, book["id"])
    except BaseException:
        _move_back(moves)
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(final, ignore_errors=True)
        raise
    _clean_empty(library, folder_relative)
    return entry_id


def trash_edition(library: Library, book: dict, edition: dict) -> str:
    entry_id = uuid.uuid4().hex
    temporary = library.trash_path(f".tmp-{entry_id}")
    files_root = temporary / "files"
    files_root.mkdir(parents=True)
    final = library.trash_path(entry_id)
    moves: list[tuple[Path, Path]] = []
    folder_relative = book.get("folder") or ""
    files = edition.get("files") or []
    try:
        relative_paths = []
        if edition.get("is_folder"):
            relative_paths.append(edition["path"])
        else:
            for item in files or [{"path": edition["path"]}]:
                relative_paths.append(item["path"])
        for relative in relative_paths:
            source = library.path(relative)
            if source.exists():
                target = files_root / relative
                _move(source, target)
                moves.append((target, source))
        covers = []
        for name in _cover_names({}, [edition]):
            for kind in ("covers", "thumbnails"):
                source = library.root / kind / name
                if source.is_file():
                    target = files_root / kind / name
                    _move(source, target)
                    moves.append((target, source))
                    covers.append({"kind": kind, "name": name})
        manifest = {
            "id": entry_id,
            "kind": "edition",
            "deleted_at": db.now_iso(),
            "title": f"{book.get('title') or 'Untitled'} — {edition.get('kind')} edition",
            "authors": book.get("authors") or [],
            "book_id": book["id"],
            "book_title": book.get("title") or "Untitled",
            "book_folder": folder_relative,
            "edition": edition,
            "covers": covers,
            "size": _tree_size(files_root),
        }
        _write_manifest(temporary, manifest)
        os.replace(temporary, final)
        moves = [
            (final / current.relative_to(temporary), original)
            for current, original in moves
        ]
        with db.session(library.db_path) as connection:
            db.delete_edition(connection, edition["id"])
    except BaseException:
        _move_back(moves)
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(final, ignore_errors=True)
        raise
    _clean_empty(library, folder_relative)
    return entry_id


def park_replaced(
    library: Library, book: dict, edition: dict, original_name: str
) -> dict:
    entry_id = uuid.uuid4().hex
    directory = library.trash_path(f"replaced-{entry_id}")
    files_root = directory / "files"
    files_root.mkdir(parents=True)
    moves: list[tuple[Path, Path]] = []
    relative_paths = []
    if edition.get("is_folder"):
        relative_paths.append(edition["path"])
    else:
        for item in edition.get("files") or [{"path": edition["path"]}]:
            relative_paths.append(item["path"])
    try:
        for relative in relative_paths:
            source = library.path(relative)
            if source.exists():
                target = files_root / relative
                _move(source, target)
                moves.append((target, source))
        manifest = {
            "id": f"replaced-{entry_id}",
            "kind": "file",
            "deleted_at": db.now_iso(),
            "title": f"Replaced file for {book.get('title') or 'Untitled'}",
            "authors": book.get("authors") or [],
            "book_id": book["id"],
            "edition_id": edition["id"],
            "original_name": original_name,
            "size": _tree_size(files_root),
        }
        _write_manifest(directory, manifest)
    except BaseException:
        _move_back(moves)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return {"directory": directory, "moves": moves}


def unpark(handle: dict) -> None:
    _move_back(handle.get("moves") or [])
    shutil.rmtree(handle.get("directory"), ignore_errors=True)


def entries(library: Library) -> list[dict]:
    trash = library.trash_path()
    if not trash.is_dir():
        return []
    result = []
    for directory in trash.iterdir():
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        manifest = _read_manifest(directory)
        if manifest is None:
            continue
        if manifest.get("kind") not in {"book", "edition"}:
            continue
        result.append(
            {
                "id": directory.name,
                "kind": manifest.get("kind"),
                "title": manifest.get("title") or "Untitled",
                "authors": manifest.get("authors") or [],
                "deleted_at": manifest.get("deleted_at") or "",
                "size": int(manifest.get("size") or 0),
                "restorable": True,
            }
        )
    result.sort(key=lambda item: item["deleted_at"], reverse=True)
    return result


def total_size(library: Library) -> int:
    trash = library.trash_path()
    return _tree_size(trash) if trash.is_dir() else 0


def empty(library: Library) -> int:
    trash = library.trash_path()
    if not trash.is_dir():
        return 0
    removed = 0
    for child in list(trash.iterdir()):
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass
        removed += 1
    return removed


def _remap(relative: str, old_folder: str, new_folder: str) -> str:
    if not relative:
        return ""
    if old_folder and (relative == old_folder or relative.startswith(old_folder + "/")):
        suffix = relative[len(old_folder):]
        return new_folder + suffix
    if new_folder:
        return new_folder + "/" + Path(relative).name
    return relative


def _restore_covers(
    library: Library,
    entry_directory: Path,
    covers: list[dict],
    moves: list[tuple[Path, Path]],
) -> dict[tuple[str, str], str]:
    mapping = {}
    for item in covers:
        kind = item.get("kind")
        name = item.get("name")
        if kind not in {"covers", "thumbnails"} or not name:
            continue
        source = entry_directory / "files" / kind / name
        if not source.is_file():
            continue
        target = naming.free_path(library.root / kind, name)
        _move(source, target)
        moves.append((target, source))
        mapping[(kind, name)] = target.name
    return mapping


def _apply_cover_map(
    library: Library, item: dict, mapping: dict[tuple[str, str], str]
) -> None:
    for key, kind in (("cover", "covers"), ("thumbnail", "thumbnails")):
        name = item.get(key) or ""
        if not name:
            continue
        mapped = mapping.get((kind, name))
        if mapped:
            item[key] = mapped
        elif not (library.root / kind / name).is_file():
            item[key] = ""


def _restore_book(library: Library, entry_directory: Path, manifest: dict) -> dict:
    book = manifest.get("book") or {}
    book["editions"] = [dict(edition) for edition in book.get("editions") or []]
    for edition in book["editions"]:
        edition["files"] = [dict(item) for item in edition.get("files") or []]
    authors = book.get("authors") or []
    old_folder = manifest.get("folder") or book.get("folder") or ""
    files_root = entry_directory / "files"
    moves: list[tuple[Path, Path]] = []
    created: list[Path] = []
    stored_folder = files_root / old_folder if old_folder else None
    new_folder = ""
    if stored_folder is not None and stored_folder.exists():
        author_directory = library.root / naming.author_folder(
            authors[0] if authors else ""
        )
        _ensure(author_directory, created)
        name = naming.unique_entry(
            author_directory, naming.sanitize(book.get("title") or "Untitled")
        )
        destination = author_directory / name
        _move(stored_folder, destination)
        moves.append((destination, stored_folder))
        new_folder = library.relative(destination)
    mapping = _restore_covers(
        library, entry_directory, manifest.get("covers") or [], moves
    )
    book["folder"] = new_folder
    for edition in book["editions"]:
        edition["path"] = _remap(edition.get("path") or "", old_folder, new_folder)
        for item in edition["files"]:
            item["path"] = _remap(item.get("path") or "", old_folder, new_folder)
        _apply_cover_map(library, edition, mapping)
    _apply_cover_map(library, book, mapping)
    try:
        with db.session(library.db_path) as connection:
            book_id = db.insert_book_full(connection, book)
    except BaseException:
        _move_back(moves)
        for directory in reversed(created):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    shutil.rmtree(entry_directory, ignore_errors=True)
    return {"kind": "book", "book_id": book_id}


def _book_directory(library: Library, book: dict) -> tuple[Path, list[Path]]:
    created: list[Path] = []
    stored = book.get("folder") or ""
    if stored:
        directory = library.path(stored)
        _ensure(directory, created)
        return directory, created
    author_directory = library.root / naming.author_folder(
        (book.get("authors") or [""])[0]
    )
    _ensure(author_directory, created)
    name = naming.unique_entry(
        author_directory, naming.sanitize(book.get("title") or "Untitled")
    )
    directory = author_directory / name
    _ensure(directory, created)
    return directory, created


def _restore_edition(library: Library, entry_directory: Path, manifest: dict) -> dict:
    stored_edition = manifest.get("edition") or {}
    edition = dict(stored_edition)
    edition["files"] = [dict(item) for item in edition.get("files") or []]
    files_root = entry_directory / "files"
    moves: list[tuple[Path, Path]] = []
    created: list[Path] = []
    try:
        with db.session(library.db_path) as connection:
            book = db.get_book(connection, int(manifest.get("book_id") or 0))
            if book is None:
                raise TrashError(
                    "the book for this edition no longer exists, so the edition cannot be restored"
                )
            if any(item["kind"] == edition.get("kind") for item in book["editions"]):
                raise TrashError("this book already has an edition of that format")
            book_directory, created = _book_directory(library, book)
            book_relative = library.relative(book_directory)
            if book.get("folder") != book_relative:
                db.update_book(connection, book["id"], {"folder": book_relative})
            audio_directory = None
            if edition.get("kind") == "audiobook":
                audio_directory = book_directory / "audio"
                _ensure(audio_directory, created)
            new_files = []
            if edition.get("is_folder"):
                source = files_root / edition["path"]
                if not source.is_dir():
                    raise TrashError("the edition files are missing from the trash")
                destination = audio_directory
                if destination.exists() and any(destination.iterdir()):
                    destination = book_directory / naming.unique_entry(
                        book_directory, "audio"
                    )
                    _ensure(destination, created)
                _move(source, destination)
                moves.append((destination, source))
                edition["path"] = library.relative(destination)
                for item in edition["files"]:
                    new_files.append(
                        {
                            **item,
                            "path": library.relative(
                                destination / Path(item["path"]).name
                            ),
                        }
                    )
            else:
                for item in edition["files"]:
                    source = files_root / item["path"]
                    if not source.is_file():
                        raise TrashError("the edition files are missing from the trash")
                    base = book_directory if edition.get("kind") == "ebook" else audio_directory
                    _ensure(base, created)
                    target = naming.free_path(base, Path(item["path"]).name)
                    _move(source, target)
                    moves.append((target, source))
                    new_files.append({**item, "path": library.relative(target)})
                if new_files:
                    edition["path"] = new_files[0]["path"]
            edition["files"] = new_files
            mapping = _restore_covers(
                library, entry_directory, manifest.get("covers") or [], moves
            )
            _apply_cover_map(library, edition, mapping)
            edition_id = db.insert_edition(
                connection, book["id"], edition, new_files
            )
    except BaseException:
        _move_back(moves)
        for directory in reversed(created):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    shutil.rmtree(entry_directory, ignore_errors=True)
    return {"kind": "edition", "book_id": book["id"], "edition_id": edition_id}


def restore(library: Library, entry_id: str) -> dict:
    directory = _entry_directory(library, entry_id)
    if not directory.is_dir():
        raise TrashError("this trash entry no longer exists")
    manifest = _read_manifest(directory)
    if manifest is None:
        raise TrashError("this trash entry is damaged")
    if manifest.get("kind") == "book":
        return _restore_book(library, directory, manifest)
    if manifest.get("kind") == "edition":
        return _restore_edition(library, directory, manifest)
    raise TrashError("this trash entry cannot be restored")
