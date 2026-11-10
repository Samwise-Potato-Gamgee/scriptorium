# SQLite schema and queries for books, authors, subgenres, genres,
# editions and edition files.
from __future__ import annotations

import datetime as dt
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .naming import author_sort_key
from .textutil import clean_series_number, clean_status

DEFAULT_GENRES = [
    "Science Fiction",
    "Fantasy",
    "Mystery & Thriller",
    "Romance",
    "Historical Fiction",
    "Horror",
    "Literary Fiction",
    "Biography & Memoir",
    "History",
    "Science & Technology",
    "Self-Help",
    "Business & Economics",
    "Philosophy",
    "Other",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS genres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author_sort TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    series TEXT NOT NULL DEFAULT '',
    series_number TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'unread',
    genre TEXT NOT NULL DEFAULT 'Other',
    needs_review INTEGER NOT NULL DEFAULT 0,
    imported_from TEXT NOT NULL DEFAULT '',
    imported_from_kind TEXT NOT NULL DEFAULT 'file',
    added_at TEXT NOT NULL,
    folder TEXT NOT NULL DEFAULT '',
    cover TEXT NOT NULL DEFAULT '',
    thumbnail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS books_title ON books(title);
CREATE TABLE IF NOT EXISTS book_authors (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS book_authors_book ON book_authors(book_id);
CREATE INDEX IF NOT EXISTS book_authors_name ON book_authors(name);
CREATE TABLE IF NOT EXISTS book_subgenres (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS book_subgenres_book ON book_subgenres(book_id);
CREATE TABLE IF NOT EXISTS editions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    is_folder INTEGER NOT NULL DEFAULT 0,
    path TEXT NOT NULL,
    duration REAL NOT NULL DEFAULT 0,
    narrator TEXT NOT NULL DEFAULT '',
    cover TEXT NOT NULL DEFAULT '',
    thumbnail TEXT NOT NULL DEFAULT '',
    imported_from TEXT NOT NULL DEFAULT '',
    imported_from_kind TEXT NOT NULL DEFAULT 'file'
);
CREATE UNIQUE INDEX IF NOT EXISTS editions_book_kind ON editions(book_id, kind);
CREATE TABLE IF NOT EXISTS edition_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    edition_id INTEGER NOT NULL REFERENCES editions(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    size INTEGER NOT NULL DEFAULT 0,
    checksum TEXT NOT NULL DEFAULT '',
    duration REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS edition_files_edition ON edition_files(edition_id);
"""

BOOK_COLUMNS = (
    "title",
    "author_sort",
    "description",
    "series",
    "series_number",
    "status",
    "genre",
    "needs_review",
    "imported_from",
    "imported_from_kind",
    "added_at",
    "folder",
    "cover",
    "thumbnail",
)

EDITION_COLUMNS = (
    "kind",
    "is_folder",
    "path",
    "duration",
    "narrator",
    "cover",
    "thumbnail",
    "imported_from",
    "imported_from_kind",
)

SUMMARY_QUERY = """
SELECT b.*,
    (SELECT COUNT(*) FROM editions e WHERE e.book_id = b.id AND e.kind = 'ebook') AS ebook_count,
    (SELECT COUNT(*) FROM editions e WHERE e.book_id = b.id AND e.kind = 'audiobook') AS audiobook_count,
    (SELECT COALESCE(SUM(e.duration), 0) FROM editions e WHERE e.book_id = b.id) AS total_duration,
    (SELECT e.narrator FROM editions e WHERE e.book_id = b.id AND e.kind = 'audiobook' LIMIT 1) AS narrator,
    (SELECT e.cover FROM editions e WHERE e.book_id = b.id AND e.kind = 'audiobook' LIMIT 1) AS audiobook_cover,
    (SELECT e.thumbnail FROM editions e WHERE e.book_id = b.id AND e.kind = 'audiobook' LIMIT 1) AS audiobook_thumbnail
FROM books b
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fold(value) -> str:
    return str(value or "").casefold()


@contextmanager
def session(db_path: Path):
    connection = sqlite3.connect(str(db_path), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.create_function("fold", 1, fold)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_schema(connection: sqlite3.Connection) -> None:
    if not connection.in_transaction:
        connection.execute("BEGIN")
    for statement in SCHEMA.split(";"):
        if statement.strip():
            connection.execute(statement)
    connection.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '1')"
    )
    if not connection.execute("SELECT 1 FROM genres LIMIT 1").fetchone():
        set_genres(connection, DEFAULT_GENRES)


def list_genres(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM genres ORDER BY position, name"
    ).fetchall()
    return [row["name"] for row in rows]


def set_genres(connection: sqlite3.Connection, names: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for name in names or []:
        value = str(name or "").strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            cleaned.append(value)
    if not any(name.casefold() == "other" for name in cleaned):
        cleaned.append("Other")
    connection.execute("DELETE FROM genres")
    for position, name in enumerate(cleaned):
        connection.execute(
            "INSERT INTO genres (name, position) VALUES (?, ?)", (name, position)
        )
    return cleaned


def _row_to_summary(row: sqlite3.Row) -> dict:
    book = dict(row)
    book["needs_review"] = bool(book["needs_review"])
    book["has_ebook"] = bool(book.pop("ebook_count", 0))
    book["has_audiobook"] = bool(book.pop("audiobook_count", 0))
    book["authors"] = []
    book["subgenres"] = []
    return book


def _attach_meta(connection: sqlite3.Connection, books: list[dict]) -> None:
    if not books:
        return
    identifiers = [book["id"] for book in books]
    placeholders = ",".join("?" for _ in identifiers)
    authors = {}
    for row in connection.execute(
        f"SELECT book_id, name FROM book_authors WHERE book_id IN ({placeholders}) "
        "ORDER BY position",
        identifiers,
    ):
        authors.setdefault(row["book_id"], []).append(row["name"])
    subgenres = {}
    for row in connection.execute(
        f"SELECT book_id, name FROM book_subgenres WHERE book_id IN ({placeholders}) "
        "ORDER BY position",
        identifiers,
    ):
        subgenres.setdefault(row["book_id"], []).append(row["name"])
    for book in books:
        book["authors"] = authors.get(book["id"], [])
        book["subgenres"] = subgenres.get(book["id"], [])


def get_book(connection: sqlite3.Connection, book_id: int) -> dict | None:
    row = connection.execute(SUMMARY_QUERY + " WHERE b.id = ?", (book_id,)).fetchone()
    if row is None:
        return None
    book = _row_to_summary(row)
    _attach_meta(connection, [book])
    book["editions"] = []
    for edition_row in connection.execute(
        "SELECT * FROM editions WHERE book_id = ? ORDER BY CASE kind "
        "WHEN 'ebook' THEN 0 ELSE 1 END",
        (book_id,),
    ):
        edition = dict(edition_row)
        edition["is_folder"] = bool(edition["is_folder"])
        edition["files"] = [
            dict(file_row)
            for file_row in connection.execute(
                "SELECT * FROM edition_files WHERE edition_id = ? ORDER BY position",
                (edition["id"],),
            )
        ]
        book["editions"].append(edition)
    return book


def get_edition(connection: sqlite3.Connection, edition_id: int) -> dict | None:
    row = connection.execute(
        "SELECT * FROM editions WHERE id = ?", (edition_id,)
    ).fetchone()
    if row is None:
        return None
    edition = dict(row)
    edition["is_folder"] = bool(edition["is_folder"])
    edition["files"] = [
        dict(file_row)
        for file_row in connection.execute(
            "SELECT * FROM edition_files WHERE edition_id = ? ORDER BY position",
            (edition_id,),
        )
    ]
    return edition


def _like(value: str) -> str:
    escaped = value.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filters(
    q: str = "",
    genre: str = "",
    subgenre: str = "",
    status: str = "",
    edition: str = "",
    review: bool = False,
) -> tuple[str, list]:
    clauses = ["1 = 1"]
    parameters: list = []
    if q.strip():
        pattern = _like(q.strip())
        clauses.append(
            "(fold(b.title) LIKE ? ESCAPE '\\'"
            " OR fold(b.description) LIKE ? ESCAPE '\\'"
            " OR fold(b.series) LIKE ? ESCAPE '\\'"
            " OR EXISTS (SELECT 1 FROM book_authors a WHERE a.book_id = b.id"
            "            AND fold(a.name) LIKE ? ESCAPE '\\')"
            " OR EXISTS (SELECT 1 FROM editions e WHERE e.book_id = b.id"
            "            AND fold(e.narrator) LIKE ? ESCAPE '\\'))"
        )
        parameters.extend([pattern] * 5)
    if genre.strip():
        clauses.append("fold(b.genre) = fold(?)")
        parameters.append(genre.strip())
    if subgenre.strip():
        clauses.append(
            "EXISTS (SELECT 1 FROM book_subgenres s WHERE s.book_id = b.id"
            " AND fold(s.name) = fold(?))"
        )
        parameters.append(subgenre.strip())
    if status.strip():
        clauses.append("b.status = ?")
        parameters.append(status.strip())
    if edition.strip():
        clauses.append(
            "EXISTS (SELECT 1 FROM editions e WHERE e.book_id = b.id AND e.kind = ?)"
        )
        parameters.append(edition.strip())
    if review:
        clauses.append("b.needs_review = 1")
    return " AND ".join(clauses), parameters


def _order(sort: str, direction: str) -> str:
    descending = direction.casefold() == "desc"
    suffix = "DESC" if descending else "ASC"
    if sort == "author":
        return f"fold(b.author_sort) {suffix}, fold(b.title) ASC"
    if sort == "series":
        return (
            f"CASE WHEN b.series = '' THEN 1 ELSE 0 END ASC, "
            f"fold(b.series) {suffix}, "
            f"CASE WHEN b.series_number = '' THEN 1 ELSE 0 END ASC, "
            f"CAST(b.series_number AS REAL) {suffix}, fold(b.title) ASC"
        )
    if sort == "added":
        return f"b.added_at {suffix}, b.id {suffix}"
    if sort == "status":
        return f"b.status {suffix}, fold(b.title) ASC"
    if sort == "genre":
        return f"fold(b.genre) {suffix}, fold(b.title) ASC"
    return f"fold(b.title) {suffix}, b.id {suffix}"


def list_books(
    connection: sqlite3.Connection,
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
) -> tuple[list[dict], int]:
    where, parameters = _filters(q, genre, subgenre, status, edition, review)
    total = connection.execute(
        "SELECT COUNT(*) FROM books b WHERE " + where, parameters
    ).fetchone()[0]
    rows = connection.execute(
        SUMMARY_QUERY
        + " WHERE "
        + where
        + " ORDER BY "
        + _order(sort, direction)
        + " LIMIT ? OFFSET ?",
        [*parameters, max(1, min(limit, 200)), max(0, offset)],
    ).fetchall()
    books = [_row_to_summary(row) for row in rows]
    _attach_meta(connection, books)
    return books, total


def home_data(connection: sqlite3.Connection) -> dict:
    recent_rows = connection.execute(
        SUMMARY_QUERY + " ORDER BY b.added_at DESC, b.id DESC LIMIT 12"
    ).fetchall()
    unread_rows = connection.execute(
        SUMMARY_QUERY + " WHERE b.status = 'unread' ORDER BY b.added_at DESC, b.id DESC LIMIT 12"
    ).fetchall()
    recent = [_row_to_summary(row) for row in recent_rows]
    unread = [_row_to_summary(row) for row in unread_rows]
    _attach_meta(connection, recent + unread)
    books = connection.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    ebooks = connection.execute(
        "SELECT COUNT(DISTINCT book_id) FROM editions WHERE kind = 'ebook'"
    ).fetchone()[0]
    audiobooks = connection.execute(
        "SELECT COUNT(DISTINCT book_id) FROM editions WHERE kind = 'audiobook'"
    ).fetchone()[0]
    seconds = connection.execute(
        "SELECT COALESCE(SUM(duration), 0) FROM editions WHERE kind = 'audiobook'"
    ).fetchone()[0]
    return {
        "recent": recent,
        "unread": unread,
        "counts": {
            "books": books,
            "ebooks": ebooks,
            "audiobooks": audiobooks,
            "listening_hours": round(float(seconds) / 3600, 1),
            "listening_seconds": int(seconds),
        },
    }


def insert_book(
    connection: sqlite3.Connection,
    book: dict,
    authors: list[str],
    subgenres: list[str],
) -> int:
    titles = authors or []
    cursor = connection.execute(
        "INSERT INTO books (title, author_sort, description, series, series_number,"
        " status, genre, needs_review, imported_from, imported_from_kind, added_at,"
        " folder, cover, thumbnail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(book.get("title") or "Untitled"),
            book.get("author_sort")
            or (author_sort_key(titles[0]) if titles else ""),
            str(book.get("description") or ""),
            str(book.get("series") or ""),
            clean_series_number(book.get("series_number")),
            clean_status(book.get("status")),
            str(book.get("genre") or "Other"),
            1 if book.get("needs_review") else 0,
            str(book.get("imported_from") or ""),
            str(book.get("imported_from_kind") or "file"),
            str(book.get("added_at") or now_iso()),
            str(book.get("folder") or ""),
            str(book.get("cover") or ""),
            str(book.get("thumbnail") or ""),
        ),
    )
    book_id = int(cursor.lastrowid)
    replace_authors(connection, book_id, authors)
    replace_subgenres(connection, book_id, subgenres)
    return book_id


def insert_book_full(connection: sqlite3.Connection, book: dict) -> int:
    book_id = insert_book(
        connection, book, book.get("authors") or [], book.get("subgenres") or []
    )
    for edition in book.get("editions") or []:
        insert_edition(connection, book_id, edition, edition.get("files") or [])
    return book_id


def update_book(connection: sqlite3.Connection, book_id: int, fields: dict) -> None:
    updates = {key: fields[key] for key in fields if key in BOOK_COLUMNS}
    if "needs_review" in updates:
        updates["needs_review"] = 1 if updates["needs_review"] else 0
    if "series_number" in updates:
        updates["series_number"] = clean_series_number(updates["series_number"])
    if "status" in updates:
        updates["status"] = clean_status(updates["status"])
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    connection.execute(
        f"UPDATE books SET {assignments} WHERE id = ?",
        [*updates.values(), book_id],
    )


def delete_book(connection: sqlite3.Connection, book_id: int) -> None:
    connection.execute("DELETE FROM books WHERE id = ?", (book_id,))


def replace_authors(
    connection: sqlite3.Connection, book_id: int, authors: list[str]
) -> None:
    connection.execute("DELETE FROM book_authors WHERE book_id = ?", (book_id,))
    for position, name in enumerate(authors):
        connection.execute(
            "INSERT INTO book_authors (book_id, position, name) VALUES (?, ?, ?)",
            (book_id, position, name),
        )
    connection.execute(
        "UPDATE books SET author_sort = ? WHERE id = ?",
        (author_sort_key(authors[0]) if authors else "", book_id),
    )


def replace_subgenres(
    connection: sqlite3.Connection, book_id: int, subgenres: list[str]
) -> None:
    connection.execute("DELETE FROM book_subgenres WHERE book_id = ?", (book_id,))
    for position, name in enumerate(subgenres):
        connection.execute(
            "INSERT INTO book_subgenres (book_id, position, name) VALUES (?, ?, ?)",
            (book_id, position, name),
        )


def insert_edition(
    connection: sqlite3.Connection,
    book_id: int,
    edition: dict,
    files: list[dict],
) -> int:
    cursor = connection.execute(
        "INSERT INTO editions (book_id, kind, is_folder, path, duration, narrator,"
        " cover, thumbnail, imported_from, imported_from_kind)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            book_id,
            str(edition.get("kind") or "ebook"),
            1 if edition.get("is_folder") else 0,
            str(edition.get("path") or ""),
            float(edition.get("duration") or 0),
            str(edition.get("narrator") or ""),
            str(edition.get("cover") or ""),
            str(edition.get("thumbnail") or ""),
            str(edition.get("imported_from") or ""),
            str(edition.get("imported_from_kind") or "file"),
        ),
    )
    edition_id = int(cursor.lastrowid)
    replace_edition_files(connection, edition_id, files)
    return edition_id


def update_edition(
    connection: sqlite3.Connection, edition_id: int, fields: dict
) -> None:
    updates = {key: fields[key] for key in fields if key in EDITION_COLUMNS}
    if "is_folder" in updates:
        updates["is_folder"] = 1 if updates["is_folder"] else 0
    if "duration" in updates:
        updates["duration"] = float(updates["duration"] or 0)
    if not updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in updates)
    connection.execute(
        f"UPDATE editions SET {assignments} WHERE id = ?",
        [*updates.values(), edition_id],
    )


def replace_edition_files(
    connection: sqlite3.Connection, edition_id: int, files: list[dict]
) -> None:
    connection.execute("DELETE FROM edition_files WHERE edition_id = ?", (edition_id,))
    for position, item in enumerate(files):
        connection.execute(
            "INSERT INTO edition_files (edition_id, path, position, size, checksum,"
            " duration) VALUES (?, ?, ?, ?, ?, ?)",
            (
                edition_id,
                str(item.get("path") or ""),
                int(item.get("position", position)),
                int(item.get("size") or 0),
                str(item.get("checksum") or ""),
                float(item.get("duration") or 0),
            ),
        )


def delete_edition(connection: sqlite3.Connection, edition_id: int) -> None:
    connection.execute("DELETE FROM editions WHERE id = ?", (edition_id,))


def find_duplicates(
    connection: sqlite3.Connection, title: str, author: str
) -> list[dict]:
    if not title.strip():
        return []
    if author.strip():
        rows = connection.execute(
            SUMMARY_QUERY
            + " WHERE fold(b.title) = fold(?) AND EXISTS (SELECT 1 FROM book_authors a"
            " WHERE a.book_id = b.id AND a.position = 0 AND fold(a.name) = fold(?))"
            " ORDER BY b.id",
            (title, author),
        ).fetchall()
    else:
        rows = connection.execute(
            SUMMARY_QUERY
            + " WHERE fold(b.title) = fold(?) AND NOT EXISTS (SELECT 1 FROM book_authors a"
            " WHERE a.book_id = b.id) ORDER BY b.id",
            (title,),
        ).fetchall()
    books = [_row_to_summary(row) for row in rows]
    _attach_meta(connection, books)
    return books


def suggest_authors(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT MIN(name) AS name FROM book_authors GROUP BY fold(name)"
    ).fetchall()
    return [row["name"] for row in rows]


def suggest_series(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT series, MIN(id) AS first_id FROM books WHERE series <> ''"
        " GROUP BY fold(series) ORDER BY fold(series)"
    ).fetchall()
    return [row["series"] for row in rows]


def suggest_subgenres(connection: sqlite3.Connection, genre: str = "") -> list[str]:
    if genre.strip():
        rows = connection.execute(
            "SELECT s.name, MIN(s.book_id) AS first_id FROM book_subgenres s"
            " JOIN books b ON b.id = s.book_id WHERE fold(b.genre) = fold(?)"
            " GROUP BY fold(s.name) ORDER BY fold(s.name)",
            (genre,),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT name, MIN(book_id) AS first_id FROM book_subgenres"
            " GROUP BY fold(name) ORDER BY fold(name)"
        ).fetchall()
    return [row["name"] for row in rows]


def series_summary(connection: sqlite3.Connection) -> list[dict]:
    groups: dict[str, dict] = {}
    for row in connection.execute(
        "SELECT series FROM books WHERE series <> '' ORDER BY series"
    ):
        name = row["series"]
        key = name.casefold()
        if key not in groups:
            groups[key] = {"name": name, "count": 0}
        groups[key]["count"] += 1
    return sorted(groups.values(), key=lambda item: item["name"].casefold())


def series_books(connection: sqlite3.Connection, name: str) -> list[dict]:
    rows = connection.execute(
        SUMMARY_QUERY
        + " WHERE fold(b.series) = fold(?)"
        " ORDER BY CASE WHEN b.series_number = '' THEN 1 ELSE 0 END,"
        " CAST(b.series_number AS REAL), fold(b.title)",
        (name,),
    ).fetchall()
    books = [_row_to_summary(row) for row in rows]
    _attach_meta(connection, books)
    return books
