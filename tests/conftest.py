# Shared pytest fixtures: temporary libraries and generated sample files.
from __future__ import annotations

import pytest

from scriptorium import db, importer
from scriptorium.library import Library
from tests.samples import generate_epub, generate_m4a, generate_mp3


@pytest.fixture
def library(tmp_path):
    return Library.create(tmp_path / "library")


@pytest.fixture
def epub_file(tmp_path):
    def make(name="source.epub", **kwargs):
        return generate_epub(tmp_path / name, **kwargs)

    return make


@pytest.fixture
def mp3_file(tmp_path):
    def make(name="source.mp3", **kwargs):
        return generate_mp3(tmp_path / name, **kwargs)

    return make


@pytest.fixture
def m4a_file(tmp_path):
    def make(name="source.m4a", **kwargs):
        return generate_m4a(tmp_path / name, **kwargs)

    return make


@pytest.fixture
def import_book():
    def run(library, path, keep_original=False, **overrides):
        found = importer.inspect_source(library, str(path))
        book = {
            "title": found["metadata"]["title"],
            "authors": found["metadata"]["authors"],
            "description": found["metadata"]["description"],
            "series": found["metadata"]["series"],
            "series_number": found["metadata"]["series_number"],
            "status": "unread",
            "genre": "Science Fiction",
            "subgenres": [],
        }
        book.update(overrides)
        payload = {
            "path": str(path),
            "format": found["format"],
            "mode": "new",
            "keep_original": keep_original,
            "book": book,
            "edition": {"narrator": found["metadata"]["narrator"]},
        }
        return importer.import_source(library, payload)

    return run


@pytest.fixture
def read_book():
    def run(library, book_id):
        with db.session(library.db_path) as connection:
            return db.get_book(connection, book_id)

    return run
