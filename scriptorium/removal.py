# Deleting books and removing editions, with files and metadata going
# to the trash so they can be restored.
from __future__ import annotations

from . import db, trash
from .library import Library


class RemovalError(Exception):
    pass


def remove_edition(
    library: Library, edition_id: int, delete_book: bool = False
) -> dict:
    with db.session(library.db_path) as connection:
        edition = db.get_edition(connection, int(edition_id))
        book = db.get_book(connection, edition["book_id"]) if edition else None
    if edition is None or book is None:
        raise RemovalError("this edition no longer exists")
    if len(book["editions"]) == 1:
        if not delete_book:
            raise RemovalError(
                "this is the last edition; confirm deleting the whole book instead"
            )
        entry = trash.trash_book(library, book)
        return {"kind": "book", "entry": entry, "book_id": book["id"], "deleted_book": True}
    entry = trash.trash_edition(library, book, edition)
    return {
        "kind": "edition",
        "entry": entry,
        "book_id": book["id"],
        "deleted_book": False,
    }


def delete_book(library: Library, book_id: int) -> dict:
    with db.session(library.db_path) as connection:
        book = db.get_book(connection, int(book_id))
    if book is None:
        raise RemovalError("this book no longer exists")
    entry = trash.trash_book(library, book)
    return {"kind": "book", "entry": entry, "book_id": book["id"]}
