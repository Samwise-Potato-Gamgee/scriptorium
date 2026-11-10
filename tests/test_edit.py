# Tests for editing fields, safe folder/file renaming, covers and bulk edits.
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scriptorium import db, editing
from tests.samples import make_cover


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_edit_renames_folder_and_files(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    old_folder = library.path(book["folder"])
    checksum = digest(library.path(book["editions"][0]["path"]))
    updated = editing.update_book(
        library,
        book["id"],
        {
            "title": "Dune Messiah",
            "description": "New description",
            "series": "Dune",
            "series_number": "2",
            "status": "read",
            "genre": "Fantasy",
            "needs_review": False,
        },
        authors=["Frank Herbert", "Kevin J. Anderson"],
        subgenres=["Space Opera", "politics"],
    )
    assert updated["title"] == "Dune Messiah"
    assert updated["authors"] == ["Frank Herbert", "Kevin J. Anderson"]
    assert updated["subgenres"] == ["Space Opera", "politics"]
    assert updated["series_number"] == "2"
    assert updated["status"] == "read"
    assert updated["genre"] == "Fantasy"
    assert updated["folder"] == "Frank Herbert/Dune Messiah"
    assert not old_folder.exists()
    new_file = library.path(updated["editions"][0]["path"])
    assert new_file == library.root / "Frank Herbert" / "Dune Messiah" / "Dune Messiah.epub"
    assert new_file.is_file()
    assert digest(new_file) == checksum
    assert updated["editions"][0]["files"][0]["checksum"] == checksum


def test_changing_first_author_moves_the_folder(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    old_folder = library.path(book["folder"])
    updated = editing.update_book(library, book["id"], {}, authors=["Brian Herbert"])
    assert updated["folder"] == "Brian Herbert/Dune"
    assert not old_folder.exists()
    assert library.path(updated["editions"][0]["path"]).is_file()


def test_edit_name_clash_gets_number_suffix(library, epub_file, import_book, read_book):
    first = import_book(library, epub_file("one.epub", title="Dune"))
    second = import_book(library, epub_file("two.epub", title="Dune Messiah"))
    second_book = read_book(library, second["book_id"])
    updated = editing.update_book(library, second_book["id"], {"title": "Dune"})
    assert updated["folder"] == "Frank Herbert/Dune (2)"
    first_book = read_book(library, first["book_id"])
    assert first_book["folder"] == "Frank Herbert/Dune"
    assert library.path(updated["editions"][0]["path"]) == library.root / "Frank Herbert" / "Dune (2)" / "Dune.epub"


def test_rename_failure_rolls_back_files_and_database(library, epub_file, import_book, read_book, monkeypatch):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    old_file = library.path(book["editions"][0]["path"])
    original_rename = editing._rename_path

    def flaky(source, target):
        if str(target).endswith("Broken Rename") and Path(target).suffix == "":
            raise OSError("rename failed")
        return original_rename(source, target)

    monkeypatch.setattr(editing, "_rename_path", flaky)
    with pytest.raises(OSError):
        editing.update_book(library, book["id"], {"title": "Broken Rename"})
    after = read_book(library, book["id"])
    assert after["title"] == "Dune"
    assert after["folder"] == "Frank Herbert/Dune"
    assert old_file.is_file()
    assert not (library.root / "Frank Herbert" / "Broken Rename").exists()
    assert not (library.root / "Frank Herbert" / "Dune" / "Broken Rename.epub").exists()


def test_cover_upload_replaces_previous_cover(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    first = editing.set_cover(library, book["id"], make_cover((200, 20, 20)))
    after_first = read_book(library, book["id"])
    assert after_first["cover"] == first["cover"]
    assert library.cover_path(first["cover"]).is_file()
    assert library.thumbnail_path(first["thumbnail"]).is_file()
    second = editing.set_cover(library, book["id"], make_cover((20, 20, 200)))
    after_second = read_book(library, book["id"])
    assert after_second["cover"] == second["cover"]
    assert second["cover"] != first["cover"]
    assert not library.cover_path(first["cover"]).exists()
    assert library.cover_path(second["cover"]).is_file()


def test_edition_narrator_can_be_edited(library, mp3_file, import_book, read_book):
    result = import_book(library, mp3_file("dune.mp3", title="Dune", narrator="Old Reader"))
    book = read_book(library, result["book_id"])
    edition = book["editions"][0]
    updated = editing.update_edition_metadata(library, edition["id"], {"narrator": "New Reader"})
    audio = updated["editions"][0]
    assert audio["narrator"] == "New Reader"
    assert updated["title"] == "Dune"


def test_bulk_update_limited_fields(library, epub_file, import_book, read_book):
    first = import_book(library, epub_file("one.epub"))
    second = import_book(library, epub_file("two.epub", title="Dune Messiah"))
    count = editing.bulk_update(
        library,
        [first["book_id"], second["book_id"]],
        {"genre": "Fantasy", "status": "read", "series": "Saga", "subgenres": ["Epic"]},
    )
    assert count == 2
    for book_id in (first["book_id"], second["book_id"]):
        book = read_book(library, book_id)
        assert book["genre"] == "Fantasy"
        assert book["status"] == "read"
        assert book["series"] == "Saga"
        assert book["subgenres"] == ["Epic"]


def test_metadata_edit_without_rename_keeps_files(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    before = library.path(book["editions"][0]["path"])
    checksum = digest(before)
    updated = editing.update_book(
        library,
        book["id"],
        {"genre": "History", "description": "Changed", "status": "didnt_finish"},
    )
    after = library.path(updated["editions"][0]["path"])
    assert after == before
    assert after.is_file()
    assert digest(after) == checksum
    assert updated["genre"] == "History"
    assert updated["status"] == "didnt_finish"
