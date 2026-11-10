# Command-line interface: start the server or import a path directly.
from __future__ import annotations

import argparse
from pathlib import Path

from . import config, importer
from .library import Library, LibraryError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scriptorium",
        description="Local, offline ebook and audiobook library manager.",
    )
    parser.add_argument("command", nargs="?", help="optional command: add")
    parser.add_argument("path", nargs="?", help="file or folder to import")
    parser.add_argument(
        "--library", help="library folder to use (creates it when missing)"
    )
    parser.add_argument("--port", type=int, help="port for the local server")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the browser when starting the server",
    )
    parser.add_argument(
        "--keep-original",
        action="store_true",
        help="with 'add': leave the source file or folder where it is",
    )
    return parser


def _select_library(raw: str | None) -> Library | None:
    if raw:
        path = Path(raw).expanduser()
        if path.is_file():
            print(f"The library path is a file: {path}")
            return None
        try:
            if path.is_dir() and (path / "library.db").is_file():
                opened = Library.open(path)
            else:
                opened = Library.create(path)
        except LibraryError as error:
            print(f"The library could not be opened: {error}")
            return None
        config.update(library_path=str(opened.root))
        return opened
    stored = str(config.load().get("library_path") or "")
    if not stored:
        print(
            "No library is set yet. Start the app once and choose a library folder, "
            "or pass --library PATH."
        )
        return None
    try:
        return Library.open(stored)
    except LibraryError as error:
        print(f"The library could not be opened: {error}")
        return None


def add_path(library: Library, raw_path: str, keep_original: bool = False) -> int:
    library.cleanup_staging()
    try:
        found = importer.inspect_source(library, raw_path)
    except importer.ImportFailure as error:
        print(f"Skipped: {error}")
        return 1
    metadata = found["metadata"]
    title = metadata.get("title") or ""
    if not title:
        print(
            f"Skipped '{found['path']}': no title was found in the tags. "
            "Add it through the app's Add dialog instead."
        )
        return 1
    if found["duplicates"]:
        match = found["duplicates"][0]
        print(
            f"Skipped '{title}': a likely duplicate already exists "
            f"(book {match['id']}, {match['title']})."
        )
        return 1
    payload = {
        "path": found["path"],
        "format": found["format"],
        "mode": "new",
        "keep_original": keep_original,
        "book": {
            "title": title,
            "authors": metadata.get("authors") or [],
            "description": metadata.get("description") or "",
            "series": metadata.get("series") or "",
            "series_number": metadata.get("series_number") or "",
            "status": "unread",
            "genre": "Other",
            "subgenres": [],
            "needs_review": True,
        },
        "edition": {"narrator": metadata.get("narrator") or ""},
    }
    try:
        result = importer.import_source(library, payload)
    except importer.ImportFailure as error:
        print(f"Import failed: {error}")
        return 1
    print(f"Imported '{title}' as book {result['book_id']}, flagged for review.")
    for warning in result["warnings"]:
        print(f"Warning: {warning}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command not in (None, "add"):
        print(f"Unknown command: {arguments.command}")
        return 2
    if arguments.command == "add" and not arguments.path:
        print("Usage: python -m scriptorium add <path>")
        return 2
    library = _select_library(arguments.library)
    if arguments.command == "add":
        if library is None:
            return 2
        return add_path(
            library, arguments.path, keep_original=bool(arguments.keep_original)
        )
    from . import server

    settings = config.load()
    port = arguments.port or int(settings.get("port") or 8737)
    if arguments.port:
        config.update(port=port)
    return server.run(port, open_browser=not arguments.no_browser)
