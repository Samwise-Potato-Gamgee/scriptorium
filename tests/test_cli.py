# Tests for the command-line import behaviour.
from __future__ import annotations

from scriptorium import cli, db


def test_cli_import_flags_review(library, epub_file, read_book, capsys):
    source = epub_file("dune.epub")
    code = cli.add_path(library, str(source))
    assert code == 0
    assert not source.exists()
    with db.session(library.db_path) as connection:
        book_id = connection.execute("SELECT id FROM books").fetchone()["id"]
    book = read_book(library, book_id)
    assert book["needs_review"] is True
    assert book["genre"] == "Other"
    assert book["series"] == "Dune"
    assert "flagged for review" in capsys.readouterr().out


def test_cli_skips_missing_title(library, epub_file, capsys):
    source = epub_file("untitled.epub", title="", authors=("Someone",))
    code = cli.add_path(library, str(source))
    assert code == 1
    assert source.is_file()
    with db.session(library.db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0
    assert "no title" in capsys.readouterr().out


def test_cli_skips_likely_duplicate(library, epub_file, capsys):
    first = epub_file("one.epub")
    assert cli.add_path(library, str(first)) == 0
    second = epub_file("two.epub")
    code = cli.add_path(library, str(second))
    assert code == 1
    assert second.is_file()
    assert "duplicate" in capsys.readouterr().out.lower()


def test_cli_missing_author_goes_to_unknown(library, epub_file, read_book):
    source = epub_file("book.epub", authors=())
    assert cli.add_path(library, str(source)) == 0
    with db.session(library.db_path) as connection:
        book_id = connection.execute("SELECT id FROM books").fetchone()["id"]
    book = read_book(library, book_id)
    assert book["folder"].startswith("Unknown/")
    assert book["needs_review"] is True


def test_cli_corrupt_file_leaves_it(library, tmp_path, capsys):
    source = tmp_path / "broken.epub"
    source.write_text("bad", encoding="utf-8")
    code = cli.add_path(library, str(source))
    assert code == 1
    assert source.is_file()
    assert "readable EPUB" in capsys.readouterr().out


def test_cli_keep_original_flag_leaves_source(library, epub_file, tmp_path, monkeypatch, read_book):
    monkeypatch.setenv("SCRIPTORIUM_CONFIG_DIR", str(tmp_path / "config"))
    source = epub_file("kept.epub")
    code = cli.main(
        ["add", str(source), "--library", str(library.root), "--keep-original"]
    )
    assert code == 0
    assert source.is_file()
    with db.session(library.db_path) as connection:
        book_id = connection.execute("SELECT id FROM books").fetchone()["id"]
    book = read_book(library, book_id)
    copied = library.path(book["editions"][0]["path"])
    assert copied.is_file()
    assert copied.read_bytes() == source.read_bytes()
