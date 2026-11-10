# Tests for replacing an edition's file safely, including rollback on failure.
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scriptorium import importer, replacement, trash
from tests.samples import generate_mp3


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_replace_ebook_updates_file_and_keeps_metadata(library, epub_file, import_book, read_book):
    first = import_book(library, epub_file("one.epub"), status="read", genre="Fantasy")
    book = read_book(library, first["book_id"])
    edition = book["editions"][0]
    old_path = library.path(edition["path"])
    old_checksum = digest(old_path)
    new_source = epub_file("two.epub", title="A different title", authors=("Other Author",))
    result = replacement.replace_edition(library, edition["id"], str(new_source))
    assert not new_source.exists()
    after = read_book(library, result["book_id"])
    assert after["title"] == "Dune"
    assert after["authors"] == ["Frank Herbert"]
    assert after["status"] == "read"
    assert after["genre"] == "Fantasy"
    new_edition = after["editions"][0]
    new_path = library.path(new_edition["path"])
    assert new_path == old_path
    assert new_path.is_file()
    assert digest(new_path) != old_checksum
    assert new_edition["files"][0]["checksum"] == digest(new_path)
    assert new_edition["files"][0]["size"] == new_path.stat().st_size
    assert any((library.root / "trash").glob("replaced-*"))
    assert trash.total_size(library) > 0


def test_replace_audiobook_with_folder(library, mp3_file, import_book, read_book, tmp_path):
    source = mp3_file(
        "dune.mp3", title="Dune", artist="Frank Herbert", narrator="Simon Vance", frames=40
    )
    first = import_book(library, source)
    book = read_book(library, first["book_id"])
    edition = book["editions"][0]
    folder = tmp_path / "new-audio"
    folder.mkdir()
    generate_mp3(folder / "one.mp3", title="Dune", artist="Frank Herbert", narrator="", frames=30)
    generate_mp3(folder / "two.mp3", title="Dune", artist="Frank Herbert", narrator="", frames=50)
    result = replacement.replace_edition(library, edition["id"], str(folder))
    after = read_book(library, result["book_id"])
    audio = after["editions"][0]
    assert audio["is_folder"] is True
    assert audio["path"] == "Frank Herbert/Dune/audio"
    assert audio["narrator"] == "Simon Vance"
    assert audio["duration"] > 1.5
    names = [Path(item["path"]).name for item in audio["files"]]
    assert names == ["01 - Dune.mp3", "02 - Dune.mp3"]
    assert not folder.exists()
    assert library.path(audio["files"][0]["path"]).is_file()
    assert any((library.root / "trash").glob("replaced-*"))


def test_replace_copy_failure_keeps_old_file(library, epub_file, import_book, read_book, monkeypatch):
    first = import_book(library, epub_file("one.epub"))
    book = read_book(library, first["book_id"])
    edition = book["editions"][0]
    old_path = library.path(edition["path"])
    old_checksum = digest(old_path)
    new_source = epub_file("two.epub")

    def fail(source_path, target_path):
        raise OSError("No space left on device")

    monkeypatch.setattr(importer, "_copy", fail)
    with pytest.raises(importer.ImportFailure):
        replacement.replace_edition(library, edition["id"], str(new_source))
    assert old_path.is_file()
    assert digest(old_path) == old_checksum
    assert new_source.is_file()
    after = read_book(library, first["book_id"])
    assert after["editions"][0]["files"][0]["checksum"] == old_checksum
    assert not any((library.root / "trash").glob("replaced-*"))


def test_replace_swap_failure_restores_old_file(library, epub_file, import_book, read_book, monkeypatch):
    first = import_book(library, epub_file("one.epub"))
    book = read_book(library, first["book_id"])
    edition = book["editions"][0]
    old_path = library.path(edition["path"])
    old_checksum = digest(old_path)
    new_source = epub_file("two.epub")

    def fail(layout, staged, state):
        raise importer.ImportFailure("swap failed")

    monkeypatch.setattr(replacement, "_apply", fail)
    with pytest.raises(importer.ImportFailure):
        replacement.replace_edition(library, edition["id"], str(new_source))
    assert old_path.is_file()
    assert digest(old_path) == old_checksum
    assert new_source.is_file()
    after = read_book(library, first["book_id"])
    assert after["editions"][0]["files"][0]["checksum"] == old_checksum
    assert not any((library.root / "trash").glob("replaced-*"))
    assert not any((library.root / ".staging").iterdir())


def test_replace_with_wrong_format_is_rejected(library, epub_file, mp3_file, import_book, read_book):
    first = import_book(library, epub_file("one.epub"))
    book = read_book(library, first["book_id"])
    edition = book["editions"][0]
    old_path = library.path(edition["path"])
    audio = mp3_file("other.mp3")
    with pytest.raises(importer.ImportFailure):
        replacement.replace_edition(library, edition["id"], str(audio))
    assert old_path.is_file()
    assert audio.is_file()
    after = read_book(library, first["book_id"])
    assert after["editions"][0]["kind"] == "ebook"


def test_replace_with_keep_original_leaves_new_source(library, epub_file, import_book, read_book):
    first = import_book(library, epub_file("one.epub"))
    book = read_book(library, first["book_id"])
    edition = book["editions"][0]
    new_source = epub_file("two.epub", title="A different title", authors=("Other Author",))
    result = replacement.replace_edition(
        library, edition["id"], str(new_source), keep_original=True
    )
    assert new_source.is_file()
    after = read_book(library, result["book_id"])
    assert digest(library.path(after["editions"][0]["path"])) == digest(new_source)
    assert any((library.root / "trash").glob("replaced-*"))
