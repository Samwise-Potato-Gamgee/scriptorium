# Tests for the read-only library consistency report.
from __future__ import annotations

from scriptorium import check, removal


def tree(root):
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )


def test_clean_library_has_no_problems(library, epub_file, import_book):
    import_book(library, epub_file("dune.epub"))
    report = check.check_library(library)
    assert report["problems"] == []
    assert report["counts"] == {"missing": 0, "changed": 0, "extra": 0}
    assert report["checked_files"] == 1


def test_missing_file_is_reported(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    library.path(book["editions"][0]["path"]).unlink()
    report = check.check_library(library)
    assert any(problem["type"] == "missing_file" for problem in report["problems"])
    assert report["counts"]["missing"] >= 1


def test_missing_cover_is_reported(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    library.cover_path(book["cover"]).unlink()
    report = check.check_library(library)
    assert any(problem["type"] == "missing_cover" for problem in report["problems"])


def test_extra_file_is_reported_and_kept(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    extra = library.root / "Frank Herbert" / "Dune" / "notes.txt"
    extra.write_text("hello", encoding="utf-8")
    report = check.check_library(library)
    extra_problem = [problem for problem in report["problems"] if problem["type"] == "extra_file"]
    assert extra_problem
    assert extra_problem[0]["path"] == "Frank Herbert/Dune/notes.txt"
    assert extra.is_file()


def test_checksum_mismatch_is_reported(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    path = library.path(book["editions"][0]["path"])
    size = path.stat().st_size
    path.write_bytes(b"\x00" * size)
    report = check.check_library(library)
    assert any(problem["type"] == "checksum_mismatch" for problem in report["problems"])
    assert path.read_bytes() == b"\x00" * size
    assert report["counts"]["changed"] == 1


def test_size_mismatch_is_reported(library, epub_file, import_book, read_book):
    result = import_book(library, epub_file("dune.epub"))
    book = read_book(library, result["book_id"])
    path = library.path(book["editions"][0]["path"])
    with open(path, "ab") as handle:
        handle.write(b"extra")
    report = check.check_library(library)
    assert any(problem["type"] == "size_mismatch" for problem in report["problems"])


def test_check_never_changes_anything(library, epub_file, import_book):
    import_book(library, epub_file("dune.epub"))
    before = tree(library.root)
    check.check_library(library)
    assert tree(library.root) == before


def test_deleting_a_book_reports_no_extra_files(library, epub_file, import_book):
    result = import_book(library, epub_file("dune.epub"))
    removal.delete_book(library, result["book_id"])
    report = check.check_library(library)
    assert report["counts"]["extra"] == 0
