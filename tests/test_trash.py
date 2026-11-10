# Tests for deleting and removing editions, trash manifests, restore and empty trash.
from __future__ import annotations

import pytest

from scriptorium import db, importer, removal, trash


def test_delete_book_and_restore(library, epub_file, import_book, read_book):
    result = import_book(
        library,
        epub_file("dune.epub"),
        status="read",
        genre="Fantasy",
        subgenres=["Politics"],
        needs_review=True,
    )
    book = read_book(library, result["book_id"])
    folder = library.path(book["folder"])
    cover = library.cover_path(book["cover"])
    thumbnail = library.thumbnail_path(book["thumbnail"])
    removal.delete_book(library, book["id"])
    assert not folder.exists()
    assert not cover.exists()
    assert not thumbnail.exists()
    entries = trash.entries(library)
    assert len(entries) == 1
    assert entries[0]["kind"] == "book"
    assert entries[0]["title"] == "Dune"
    assert entries[0]["size"] > 0
    assert (library.trash_path(entries[0]["id"]) / "entry.json").is_file()
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    restored = trash.restore(library, entries[0]["id"])
    after = read_book(library, restored["book_id"])
    assert after["title"] == "Dune"
    assert after["authors"] == ["Frank Herbert"]
    assert after["status"] == "read"
    assert after["genre"] == "Fantasy"
    assert after["subgenres"] == ["Politics"]
    assert after["needs_review"] is True
    assert library.path(after["folder"]).is_dir()
    assert library.path(after["editions"][0]["path"]).is_file()
    assert library.cover_path(after["cover"]).is_file()
    assert trash.entries(library) == []
    assert trash.total_size(library) == 0


def test_remove_edition_keeps_book_and_restore_brings_it_back(library, epub_file, mp3_file, import_book, read_book):
    ebook = import_book(library, epub_file("dune.epub"))
    audio_source = mp3_file("dune.mp3", title="Dune", narrator="Simon Vance")
    found = importer.inspect_source(library, str(audio_source))
    importer.import_source(
        library,
        {
            "path": str(audio_source),
            "format": found["format"],
            "mode": "attach",
            "target_book_id": ebook["book_id"],
            "book": {},
        },
    )
    book = read_book(library, ebook["book_id"])
    audio = next(edition for edition in book["editions"] if edition["kind"] == "audiobook")
    audio_directory = library.path(audio["path"])
    result = removal.remove_edition(library, audio["id"])
    assert result["deleted_book"] is False
    assert not audio_directory.exists()
    after = read_book(library, ebook["book_id"])
    assert [edition["kind"] for edition in after["editions"]] == ["ebook"]
    entries = trash.entries(library)
    assert len(entries) == 1
    assert entries[0]["kind"] == "edition"
    restored = trash.restore(library, entries[0]["id"])
    final = read_book(library, restored["book_id"])
    assert [edition["kind"] for edition in final["editions"]] == ["ebook", "audiobook"]
    restored_audio = next(edition for edition in final["editions"] if edition["kind"] == "audiobook")
    assert library.path(restored_audio["path"]).is_file()
    assert all(library.path(item["path"]).is_file() for item in restored_audio["files"])


def test_removing_last_edition_requires_delete_confirmation(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    edition = book["editions"][0]
    with pytest.raises(removal.RemovalError):
        removal.remove_edition(library, edition["id"], delete_book=False)
    assert library.path(book["folder"]).is_dir()
    removed = removal.remove_edition(library, edition["id"], delete_book=True)
    assert removed["deleted_book"] is True
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert trash.entries(library)[0]["kind"] == "book"


def test_empty_trash_removes_everything(library, epub_file, import_book):
    result = import_book(library, epub_file("dune.epub"))
    removal.delete_book(library, result["book_id"])
    assert trash.entries(library)
    removed = trash.empty(library)
    assert removed >= 1
    assert trash.entries(library) == []
    assert trash.total_size(library) == 0
    assert not any(library.trash_path().iterdir())


def test_restore_uses_number_suffix_when_folder_is_taken(library, epub_file, import_book, read_book):
    first = import_book(library, epub_file("one.epub"))
    book = read_book(library, first["book_id"])
    removal.delete_book(library, book["id"])
    entry = trash.entries(library)[0]["id"]
    import_book(library, epub_file("two.epub"))
    restored = trash.restore(library, entry)
    after = read_book(library, restored["book_id"])
    assert after["folder"] == "Frank Herbert/Dune (2)"
    assert library.path(after["editions"][0]["path"]).is_file()


def test_restore_edition_without_its_book_reports_error(library, epub_file, mp3_file, import_book, read_book):
    ebook = import_book(library, epub_file("dune.epub"))
    audio_source = mp3_file("dune.mp3", title="Dune")
    found = importer.inspect_source(library, str(audio_source))
    importer.import_source(
        library,
        {
            "path": str(audio_source),
            "format": found["format"],
            "mode": "attach",
            "target_book_id": ebook["book_id"],
            "book": {},
        },
    )
    book = read_book(library, ebook["book_id"])
    audio = next(edition for edition in book["editions"] if edition["kind"] == "audiobook")
    removal.remove_edition(library, audio["id"])
    edition_entry = trash.entries(library)[0]["id"]
    removal.delete_book(library, ebook["book_id"])
    with pytest.raises(trash.TrashError):
        trash.restore(library, edition_entry)
    assert any((library.root / "trash").iterdir())
