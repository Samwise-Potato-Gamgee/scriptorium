# HTTP API for the local Scriptorium server: library state, books,
# imports, edits, series, settings, trash, checks and media files.
from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import (
    __version__,
    check,
    config,
    covers,
    db,
    dialogs,
    editing,
    importer,
    library,
    metadata,
    naming,
    removal,
    replacement,
    systempaths,
    trash,
)
from .library import Library, LibraryError

STATIC_DIRECTORY = Path(__file__).parent / "static"
ACCENTS = [
    {"name": "Amber/gold", "value": "#e0a13a"},
    {"name": "Indigo", "value": "#6366f1"},
    {"name": "Teal", "value": "#0d9488"},
    {"name": "Emerald green", "value": "#10b981"},
    {"name": "Rose", "value": "#f43f5e"},
    {"name": "Violet", "value": "#8b5cf6"},
    {"name": "Crimson red", "value": "#dc2626"},
    {"name": "Slate/graphite", "value": "#64748b"},
]
THEMES = {"system", "light", "dark"}


class AppState:
    def __init__(self):
        self.settings = config.load()
        self.library: Library | None = None
        self.status = "unconfigured"
        self.message = ""
        self.start()

    def start(self) -> None:
        path = str(self.settings.get("library_path") or "")
        if not path:
            self.library = None
            self.status = "unconfigured"
            self.message = ""
            return
        candidate = Path(path).expanduser()
        if not candidate.is_dir():
            self.library = None
            self.status = "missing"
            self.message = "library folder not found at this path"
            return
        if not (candidate / "library.db").is_file():
            self.library = None
            self.status = "missing"
            self.message = "this folder does not contain a library"
            return
        try:
            opened = Library.open(candidate)
        except LibraryError as error:
            self.library = None
            self.status = "missing"
            self.message = str(error)
            return
        opened.cleanup_staging()
        opened.backup()
        self.library = opened
        self.status = "ok"
        self.message = ""

    def retry(self) -> None:
        self.settings = config.load()
        self.start()

    def open(self, raw_path: str, create: bool) -> Library:
        path = Path(str(raw_path or "").strip()).expanduser()
        if not str(raw_path or "").strip():
            raise HTTPException(status_code=400, detail="a folder path is required")
        if path.is_file():
            raise HTTPException(
                status_code=400, detail="the path is a file; choose a folder"
            )
        if path.is_dir() and (path / "library.db").is_file():
            opened = Library.open(path)
        elif create:
            opened = Library.create(path)
        elif not path.exists():
            raise HTTPException(
                status_code=400, detail="the folder does not exist"
            )
        else:
            raise HTTPException(
                status_code=400, detail="no library found at this path"
            )
        opened.cleanup_staging()
        opened.backup()
        self.library = opened
        self.status = "ok"
        self.message = ""
        self.settings = config.update(library_path=str(opened.root))
        return opened

    def require(self) -> Library:
        if self.library is None:
            raise HTTPException(
                status_code=409, detail="no library is open"
            )
        return self.library

    def payload(self) -> dict:
        return {
            "library": {
                "status": self.status,
                "path": str(self.settings.get("library_path") or ""),
                "root": str(self.library.root) if self.library else "",
                "message": self.message,
            },
            "settings": {
                "theme": self.settings.get("theme") or "system",
                "accent": self.settings.get("accent") or "#e0a13a",
                "port": int(self.settings.get("port") or 8737),
                "delete_originals": bool(self.settings.get("delete_originals")),
            },
            "accents": ACCENTS,
            "themes": sorted(THEMES),
            "default_library_parent": str(systempaths.default_library_parent()),
            "version": __version__,
        }


def _series_numbers(books: list[dict]) -> list[int]:
    numbers = []
    for book in books:
        text = str(book.get("series_number") or "").strip()
        if not text:
            continue
        try:
            number = float(text)
        except ValueError:
            continue
        if number.is_integer() and number >= 0:
            numbers.append(int(number))
    return sorted(set(numbers))


def _decode_image(value) -> bytes:
    text = str(value or "")
    if not text:
        raise HTTPException(status_code=400, detail="no image was supplied")
    if text.startswith("data:"):
        parts = text.split(",", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="the image data could not be read")
        text = parts[1]
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="the image data could not be read")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="the image is too large")
    return data


def _fetch_book(library_path: Path, book_id: int) -> dict:
    with db.session(library_path) as connection:
        book = db.get_book(connection, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="book not found")
    return book


def create_app() -> FastAPI:
    state = AppState()
    app = FastAPI(
        title="Scriptorium",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.scriptorium = state

    def domain_error(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse({"error": str(error)}, status_code=400)

    for error_type in (
        importer.ImportFailure,
        editing.EditFailure,
        removal.RemovalError,
        trash.TrashError,
        LibraryError,
        metadata.InvalidFile,
        covers.CoverError,
    ):
        app.add_exception_handler(error_type, domain_error)

    def require() -> Library:
        return state.require()

    @app.get("/api/state")
    def get_state():
        return state.payload()

    @app.post("/api/library/open")
    def open_library(payload: dict = Body(...)):
        state.open(str(payload.get("path") or ""), bool(payload.get("create")))
        return state.payload()

    @app.post("/api/library/retry")
    def retry_library():
        state.retry()
        if state.library is None:
            raise HTTPException(status_code=400, detail=state.message)
        return state.payload()

    @app.get("/api/home")
    def home():
        with db.session(require().db_path) as connection:
            return db.home_data(connection)

    @app.get("/api/books")
    def books(
        q: str = "",
        genre: str = "",
        subgenre: str = "",
        status: str = "",
        edition: str = "",
        review: bool = False,
        sort: str = "title",
        direction: str = "asc",
        offset: int = 0,
        limit: int = 40,
    ):
        current = require()
        with db.session(current.db_path) as connection:
            items, total = db.list_books(
                connection,
                q=q,
                genre=genre,
                subgenre=subgenre,
                status=status,
                edition=edition,
                review=review,
                sort=sort,
                direction=direction,
                offset=offset,
                limit=limit,
            )
        return {"books": items, "total": total}

    @app.get("/api/books/{book_id}")
    def get_book(book_id: int):
        return {"book": _fetch_book(require().db_path, book_id)}

    @app.patch("/api/books/{book_id}")
    def patch_book(book_id: int, payload: dict = Body(...)):
        fields = {
            key: value
            for key, value in payload.items()
            if key not in {"authors", "subgenres"}
        }
        authors = payload.get("authors") if "authors" in payload else None
        subgenres = payload.get("subgenres") if "subgenres" in payload else None
        updated = editing.update_book(
            require(), book_id, fields, authors=authors, subgenres=subgenres
        )
        return {"book": updated}

    @app.delete("/api/books/{book_id}")
    def remove_book(book_id: int):
        result = removal.delete_book(require(), book_id)
        return {"deleted": True, "entry": result["entry"]}

    @app.post("/api/books/{book_id}/cover")
    def upload_cover(book_id: int, payload: dict = Body(...)):
        data = _decode_image(payload.get("data"))
        edition_id = payload.get("edition_id")
        saved = editing.set_cover(
            require(), book_id, data, int(edition_id) if edition_id else None
        )
        return {"book": _fetch_book(require().db_path, book_id), "cover": saved}

    @app.post("/api/books/bulk")
    def bulk(payload: dict = Body(...)):
        identifiers = payload.get("ids") or []
        fields = payload.get("fields") or {}
        count = editing.bulk_update(require(), identifiers, fields)
        return {"updated": count}

    @app.post("/api/dialog")
    def system_dialog(payload: dict = Body(...)):
        try:
            chosen = dialogs.choose(
                str(payload.get("kind") or "file"), str(payload.get("start") or "")
            )
        except dialogs.DialogBusy as error:
            raise HTTPException(status_code=409, detail=str(error))
        except dialogs.DialogUnavailable as error:
            raise HTTPException(status_code=400, detail=str(error))
        return {"path": chosen}

    @app.post("/api/inspect")
    def inspect(payload: dict = Body(...)):
        return importer.inspect_source(require(), str(payload.get("path") or ""))

    @app.post("/api/import")
    def run_import(payload: dict = Body(...)):
        request = dict(payload)
        if request.get("keep_original") is None:
            request["keep_original"] = not bool(
                state.settings.get("delete_originals")
            )
        result = importer.import_source(require(), request)
        book = _fetch_book(require().db_path, result["book_id"])
        return {"book": book, "warnings": result["warnings"]}

    @app.patch("/api/editions/{edition_id}")
    def patch_edition(edition_id: int, payload: dict = Body(...)):
        book = editing.update_edition_metadata(require(), edition_id, payload)
        return {"book": book}

    @app.post("/api/editions/{edition_id}/replace")
    def replace_file(edition_id: int, payload: dict = Body(...)):
        keep_original = payload.get("keep_original")
        if keep_original is None:
            keep_original = not bool(state.settings.get("delete_originals"))
        result = replacement.replace_edition(
            require(),
            edition_id,
            str(payload.get("path") or ""),
            payload.get("edition") or {},
            keep_original=bool(keep_original),
        )
        book = _fetch_book(require().db_path, result["book_id"])
        return {"book": book, "warnings": result["warnings"]}

    @app.delete("/api/editions/{edition_id}")
    def delete_edition(edition_id: int, delete_book: bool = False):
        result = removal.remove_edition(
            require(), edition_id, delete_book=delete_book
        )
        if result["deleted_book"]:
            return {"deleted_book": True, "entry": result["entry"]}
        book = _fetch_book(require().db_path, result["book_id"])
        return {"deleted_book": False, "book": book, "entry": result["entry"]}

    @app.get("/api/series")
    def series():
        with db.session(require().db_path) as connection:
            return {"series": db.series_summary(connection)}

    @app.get("/api/series/detail")
    def series_detail(name: str = ""):
        with db.session(require().db_path) as connection:
            items = db.series_books(connection, name.strip())
        numbers = _series_numbers(items)
        gaps = []
        if numbers:
            present = set(numbers)
            gaps = [
                number
                for number in range(numbers[0], numbers[-1] + 1)
                if number not in present
            ]
        return {"name": name.strip(), "books": items, "gaps": gaps}

    @app.get("/api/suggestions/{kind}")
    def suggestions(kind: str, q: str = "", genre: str = ""):
        with db.session(require().db_path) as connection:
            if kind == "author":
                values = sorted(
                    db.suggest_authors(connection),
                    key=lambda value: naming.author_sort_key(value),
                )
            elif kind == "series":
                values = db.suggest_series(connection)
            elif kind == "subgenre":
                values = db.suggest_subgenres(connection, genre)
            else:
                raise HTTPException(status_code=404, detail="unknown suggestion type")
        needle = q.strip().casefold()
        if needle:
            values = [value for value in values if needle in value.casefold()]
        if kind == "subgenre":
            return {"values": values}
        return {"values": values[:100]}

    @app.get("/api/settings")
    def get_settings():
        current = require()
        with db.session(current.db_path) as connection:
            genres = db.list_genres(connection)
        return {
            "library": {"path": str(current.root)},
            "settings": {
                "theme": state.settings.get("theme") or "system",
                "accent": state.settings.get("accent") or "#e0a13a",
                "port": int(state.settings.get("port") or 8737),
                "delete_originals": bool(state.settings.get("delete_originals")),
            },
            "themes": sorted(THEMES),
            "accents": ACCENTS,
            "genres": genres,
            "trash": {
                "entries": trash.entries(current),
                "size": trash.total_size(current),
            },
            "backups": current.backup_list(),
            "version": __version__,
        }

    @app.put("/api/settings")
    def put_settings(payload: dict = Body(...)):
        changes = {}
        if "theme" in payload:
            theme = str(payload.get("theme") or "")
            if theme not in THEMES:
                raise HTTPException(status_code=400, detail="invalid theme")
            changes["theme"] = theme
        if "accent" in payload:
            accent = str(payload.get("accent") or "")
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
                raise HTTPException(status_code=400, detail="invalid accent colour")
            changes["accent"] = accent.lower()
        if "port" in payload:
            try:
                port = int(payload.get("port"))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid port")
            if port < 1024 or port > 65535:
                raise HTTPException(
                    status_code=400, detail="the port must be between 1024 and 65535"
                )
            changes["port"] = port
        if "delete_originals" in payload:
            changes["delete_originals"] = bool(payload.get("delete_originals"))
        state.settings = config.update(**changes)
        return {
            "settings": {
                "theme": state.settings.get("theme"),
                "accent": state.settings.get("accent"),
                "port": int(state.settings.get("port") or 8737),
                "delete_originals": bool(state.settings.get("delete_originals")),
            }
        }

    @app.put("/api/genres")
    def put_genres(payload: dict = Body(...)):
        values = payload.get("genres") or []
        if not isinstance(values, list) or not any(str(value).strip() for value in values):
            raise HTTPException(status_code=400, detail="keep at least one genre")
        with db.session(require().db_path) as connection:
            genres = db.set_genres(connection, [str(value) for value in values])
        return {"genres": genres}

    @app.get("/api/trash")
    def get_trash():
        current = require()
        return {
            "entries": trash.entries(current),
            "size": trash.total_size(current),
        }

    @app.post("/api/trash/{entry_id}/restore")
    def restore_entry(entry_id: str):
        result = trash.restore(require(), entry_id)
        book = _fetch_book(require().db_path, result["book_id"])
        return {"book": book, "kind": result["kind"]}

    @app.post("/api/trash/empty")
    def empty_trash():
        return {"removed": trash.empty(require())}

    @app.post("/api/check")
    def run_check():
        return check.check_library(require())

    @app.get("/media/covers/{name}")
    def cover_file(name: str):
        return _media(require(), "covers", name)

    @app.get("/media/thumbnails/{name}")
    def thumbnail_file(name: str):
        return _media(require(), "thumbnails", name)

    @app.get("/")
    @app.get("/library")
    @app.get("/series")
    @app.get("/settings")
    @app.get("/book/{book_id}")
    def index(book_id: str = ""):
        return FileResponse(
            STATIC_DIRECTORY / "index.html",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(STATIC_DIRECTORY / "favicon.svg")

    app.mount(
        "/static", StaticFiles(directory=str(STATIC_DIRECTORY)), name="static"
    )
    return app


def _media(current: Library, kind: str, name: str) -> FileResponse:
    if not name or Path(name).name != name:
        raise HTTPException(status_code=404, detail="not found")
    path = current.root / kind / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(
        path, headers={"Cache-Control": "public, max-age=31536000, immutable"}
    )
