# Tests for creating and opening libraries, structure, staging cleanup and backups.
from __future__ import annotations

import sqlite3

import pytest

from scriptorium import db
from scriptorium.library import Library, LibraryError


def test_create_and_reopen_library(tmp_path):
    root = tmp_path / "library"
    library = Library.create(root)
    assert (root / "library.db").is_file()
    for name in ("covers", "thumbnails", "backups", "trash", ".staging"):
        assert (root / name).is_dir()
    reopened = Library.open(root)
    with db.session(reopened.db_path) as connection:
        genres = db.list_genres(connection)
    assert "Other" in genres
    assert "Science Fiction" in genres


def test_open_missing_folder_fails(tmp_path):
    with pytest.raises(LibraryError):
        Library.open(tmp_path / "nope")


def test_open_empty_folder_does_not_create_a_library(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(LibraryError):
        Library.open(root)
    assert not (root / "library.db").exists()


def test_staging_cleanup(tmp_path):
    library = Library.create(tmp_path / "library")
    staging = library.staging()
    (staging / "leftover.tmp").write_text("x", encoding="utf-8")
    library.cleanup_staging()
    assert not any((library.root / ".staging").iterdir())


def test_backups_keep_last_five(tmp_path):
    library = Library.create(tmp_path / "library")
    for _ in range(7):
        library.backup()
    backups = library.backup_list()
    assert len(backups) == 5
    names = sorted(backup["name"] for backup in backups)
    for name in names:
        with sqlite3.connect(library.root / "backups" / name) as connection:
            assert connection.execute("SELECT COUNT(*) FROM genres").fetchone()[0] > 0


def test_relative_paths_reject_escapes(tmp_path):
    library = Library.create(tmp_path / "library")
    with pytest.raises(LibraryError):
        library.path("../outside")
    relative = library.relative(library.root / "covers" / "x.jpg")
    assert relative == "covers/x.jpg"
