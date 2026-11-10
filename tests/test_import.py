# Tests for the safe import pipeline, folder audiobooks, duplicates and failures.
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from scriptorium import db, importer, naming
from tests.samples import generate_epub, generate_mp3, make_cover


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_import_epub_copies_verifies_and_deletes_original(library, epub_file, import_book, read_book):
    source = epub_file("dune.epub")
    result = import_book(library, source)
    assert not source.exists()
    book = read_book(library, result["book_id"])
    assert book["title"] == "Dune"
    assert book["authors"] == ["Frank Herbert"]
    assert book["series"] == "Dune"
    assert book["series_number"] == "1"
    assert book["description"] == "A desert planet."
    assert book["folder"] == "Frank Herbert/Dune"
    assert book["cover"]
    assert book["thumbnail"]
    assert (library.cover_path(book["cover"])).is_file()
    assert (library.thumbnail_path(book["thumbnail"])).is_file()
    assert book["has_ebook"] is True
    assert book["has_audiobook"] is False
    edition = book["editions"][0]
    assert edition["kind"] == "ebook"
    assert edition["path"] == "Frank Herbert/Dune/Dune.epub"
    assert edition["imported_from"] == "dune.epub"
    assert edition["files"][0]["checksum"] == digest(library.path(edition["path"]))
    assert edition["files"][0]["size"] == library.path(edition["path"]).stat().st_size


def test_import_audio_single_file(library, mp3_file, import_book, read_book):
    source = mp3_file("dune.mp3", title="Dune", artist="Frank Herbert", narrator="Simon Vance", cover=make_cover())
    result = import_book(library, source)
    assert not source.exists()
    book = read_book(library, result["book_id"])
    edition = book["editions"][0]
    assert edition["kind"] == "audiobook"
    assert edition["is_folder"] is False
    assert edition["narrator"] == "Simon Vance"
    assert edition["duration"] > 0
    assert edition["path"] == "Frank Herbert/Dune/audio/Dune.mp3"
    assert book["cover"]


def test_import_long_unusual_title_never_fails(library, epub_file, import_book, read_book):
    title = ("A/B:C*D? " * 30).strip()
    source = epub_file("odd.epub", title=title, authors=("Frank/Herbert",))
    result = import_book(library, source, title=title, authors=["Frank/Herbert"])
    book = read_book(library, result["book_id"])
    assert book["title"] == naming.collapse(title)
    assert book["authors"] == ["Frank/Herbert"]
    folder = Path(book["folder"])
    assert len(folder.name) <= naming.MAX_LENGTH
    assert folder.parts[0] == "Frank Herbert"
    assert library.path(book["editions"][0]["path"]).is_file()


def test_missing_author_imports_to_unknown_and_flags_review(library, epub_file, import_book, read_book):
    source = epub_file("book.epub", authors=())
    result = import_book(library, source, authors=[])
    book = read_book(library, result["book_id"])
    assert book["authors"] == []
    assert book["folder"].startswith("Unknown/")
    assert book["needs_review"] is True


def test_corrupt_epub_leaves_original_and_no_entry(library, tmp_path):
    source = tmp_path / "broken.epub"
    source.write_text("not an epub", encoding="utf-8")
    with pytest.raises(importer.ImportFailure):
        importer.inspect_source(library, str(source))
    with pytest.raises(importer.ImportFailure):
        importer.import_source(
            library,
            {
                "path": str(source),
                "format": "ebook",
                "mode": "new",
                "book": {"title": "Broken", "authors": ["Someone"]},
            },
        )
    assert source.read_text(encoding="utf-8") == "not an epub"
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0


def test_folder_audiobook_imports_in_play_order(library, tmp_path, import_book, read_book):
    folder = tmp_path / "chapters"
    folder.mkdir()
    first = generate_mp3(folder / "chapter 10.mp3", title="Ten", artist=None, narrator="Reader", track=None, frames=40)
    second = generate_mp3(folder / "chapter 2.mp3", title="Two", artist=None, narrator="Reader", track=None, frames=50)
    (folder / "notes.txt").write_text("stray", encoding="utf-8")
    result = import_book(library, folder)
    book = read_book(library, result["book_id"])
    edition = book["editions"][0]
    assert edition["is_folder"] is True
    assert edition["path"] == "Unknown/Two/audio"
    names = [Path(item["path"]).name for item in edition["files"]]
    assert names == ["01 - Two.mp3", "02 - Two.mp3"]
    assert edition["duration"] > 2
    assert not first.exists()
    assert not second.exists()
    assert (folder / "notes.txt").is_file()
    assert folder.is_dir()


def test_folder_audiobook_uses_track_tags(library, tmp_path, import_book, read_book):
    folder = tmp_path / "chapters"
    folder.mkdir()
    generate_mp3(folder / "a.mp3", title="Second", track=2)
    generate_mp3(folder / "b.mp3", title="First", track=1)
    result = import_book(library, folder)
    book = read_book(library, result["book_id"])
    edition = book["editions"][0]
    assert book["title"] == "First"
    assert [Path(item["path"]).name for item in edition["files"]] == [
        "01 - First.mp3",
        "02 - First.mp3",
    ]


def test_folder_with_one_bad_file_imports_nothing(library, tmp_path, import_book):
    folder = tmp_path / "chapters"
    folder.mkdir()
    good = generate_mp3(folder / "good.mp3", title="Good")
    bad = folder / "bad.mp3"
    bad.write_text("not audio", encoding="utf-8")
    with pytest.raises(importer.ImportFailure):
        import_book(library, folder)
    assert good.is_file()
    assert bad.is_file()
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert not any(library.root.glob("*/*"))
    assert not any((library.root / ".staging").iterdir())


def test_copy_failure_leaves_original_and_clean_library(library, epub_file, import_book, monkeypatch):
    source = epub_file("dune.epub")

    def fail(source_path, target_path):
        raise OSError("No space left on device")

    monkeypatch.setattr(importer, "_copy", fail)
    with pytest.raises(importer.ImportFailure):
        import_book(library, source)
    assert source.is_file()
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert not any(library.root.glob("*/*"))
    assert not any((library.root / ".staging").iterdir())


def test_folder_copy_failure_halfway_removes_partial_copies(library, tmp_path, import_book, monkeypatch):
    folder = tmp_path / "chapters"
    folder.mkdir()
    first = generate_mp3(folder / "one.mp3", title="One")
    second = generate_mp3(folder / "two.mp3", title="Two")
    original = importer._copy
    calls = {"count": 0}

    def flaky(source_path, target_path):
        calls["count"] += 1
        if calls["count"] > 1:
            raise OSError("No space left on device")
        return original(source_path, target_path)

    monkeypatch.setattr(importer, "_copy", flaky)
    with pytest.raises(importer.ImportFailure):
        import_book(library, folder)
    assert first.is_file()
    assert second.is_file()
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert not any(library.root.glob("*/*"))
    assert not any((library.root / ".staging").iterdir())


def test_failed_verification_keeps_original_and_no_entry(library, epub_file, import_book, monkeypatch):
    source = epub_file("dune.epub")

    def truncated(source_path, target_path):
        target_path.write_bytes(b"x")

    monkeypatch.setattr(importer, "_copy", truncated)
    with pytest.raises(importer.ImportFailure) as error:
        import_book(library, source)
    assert "verified" in str(error.value)
    assert source.is_file()
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert not any((library.root / ".staging").iterdir())


def test_duplicate_detection_and_separate_entries(library, epub_file, import_book):
    first_source = epub_file("one.epub")
    first = import_book(library, first_source)
    second_source = epub_file("two.epub")
    found = importer.inspect_source(library, str(second_source))
    assert [item["id"] for item in found["duplicates"]] == [first["book_id"]]
    second = import_book(library, second_source)
    with db.session(library.db_path) as connection:
        books = connection.execute("SELECT folder FROM books ORDER BY id").fetchall()
    assert [row["folder"] for row in books] == ["Frank Herbert/Dune", "Frank Herbert/Dune (2)"]


def test_attach_audiobook_to_ebook(library, epub_file, mp3_file, import_book, read_book):
    ebook_source = epub_file("dune.epub")
    first = import_book(library, ebook_source)
    audio_source = mp3_file("dune.mp3", title="Dune", artist="Frank Herbert", narrator="Simon Vance")
    found = importer.inspect_source(library, str(audio_source))
    result = importer.import_source(
        library,
        {
            "path": str(audio_source),
            "format": found["format"],
            "mode": "attach",
            "target_book_id": first["book_id"],
            "book": {},
            "edition": {"narrator": "Simon Vance"},
        },
    )
    assert result["book_id"] == first["book_id"]
    assert not audio_source.exists()
    book = read_book(library, first["book_id"])
    assert book["has_ebook"] is True
    assert book["has_audiobook"] is True
    audio = next(edition for edition in book["editions"] if edition["kind"] == "audiobook")
    assert audio["path"] == "Frank Herbert/Dune/audio/Dune.mp3"
    assert audio["narrator"] == "Simon Vance"


def test_attach_same_format_is_rejected(library, epub_file, import_book):
    first = import_book(library, epub_file("one.epub"))
    other = epub_file("two.epub", title="Other")
    with pytest.raises(importer.ImportFailure):
        importer.import_source(
            library,
            {
                "path": str(other),
                "format": "ebook",
                "mode": "attach",
                "target_book_id": first["book_id"],
                "book": {},
            },
        )
    assert other.is_file()


def test_new_import_requires_a_title(library, epub_file):
    source = epub_file("book.epub", title="", authors=("Someone",))
    with pytest.raises(importer.ImportFailure):
        importer.import_source(
            library,
            {
                "path": str(source),
                "format": "ebook",
                "mode": "new",
                "book": {"title": "", "authors": ["Someone"]},
            },
        )
    assert source.is_file()
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0


def test_source_inside_library_is_not_deleted(library, epub_file, import_book):
    source = epub_file("copy.epub", title="Inside")
    target = library.root / "manual.epub"
    shutil.copy2(source, target)
    result = import_book(library, target)
    assert target.is_file()
    assert result["warnings"]


def test_import_with_keep_original_leaves_epub_source(library, epub_file, import_book, read_book):
    source = epub_file("keep.epub")
    source_digest = digest(source)
    result = import_book(library, source, keep_original=True)
    assert source.is_file()
    assert digest(source) == source_digest
    book = read_book(library, result["book_id"])
    edition = book["editions"][0]
    copied = library.path(edition["path"])
    assert copied.is_file()
    assert digest(copied) == source_digest
    assert edition["files"][0]["checksum"] == source_digest
    assert edition["files"][0]["size"] == source.stat().st_size
    assert result["warnings"] == []


def test_folder_audiobook_with_keep_original_leaves_files(library, tmp_path, import_book, read_book):
    folder = tmp_path / "keep-chapters"
    folder.mkdir()
    first = generate_mp3(folder / "one.mp3", title="Kept", artist="Frank Herbert", track=None, frames=30)
    second = generate_mp3(folder / "two.mp3", title="Kept", artist="Frank Herbert", track=None, frames=40)
    (folder / "notes.txt").write_text("stray", encoding="utf-8")
    result = import_book(library, folder, keep_original=True)
    assert first.is_file()
    assert second.is_file()
    assert (folder / "notes.txt").is_file()
    book = read_book(library, result["book_id"])
    edition = book["editions"][0]
    assert edition["is_folder"] is True
    assert len(edition["files"]) == 2
    for item, original in zip(edition["files"], (first, second)):
        copied = library.path(item["path"])
        assert copied.is_file()
        assert digest(copied) == digest(original)
        assert item["checksum"] == digest(original)
    assert result["warnings"] == []
