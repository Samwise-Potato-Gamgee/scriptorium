# Tests for EPUB, MP3 and M4A metadata reading, junk filtering and folder ordering.
from __future__ import annotations

from pathlib import Path

import pytest

from scriptorium import metadata
from tests.samples import generate_epub, generate_m4a, generate_mp3, make_cover


def test_read_epub_metadata_and_cover(tmp_path: Path):
    path = generate_epub(tmp_path / "book.epub")
    found = metadata.read_epub(path)
    assert found["title"] == "Dune"
    assert found["authors"] == ["Frank Herbert"]
    assert found["series"] == "Dune"
    assert found["series_number"] == "1"
    assert found["description"] == "A desert planet."
    assert found["cover"]
    assert found["cover"][:2] == b"\xff\xd8"


def test_read_epub_multiple_authors(tmp_path: Path):
    path = generate_epub(
        tmp_path / "book.epub", title="Book", authors=("Frank Herbert", "Brian Herbert")
    )
    assert metadata.read_epub(path)["authors"] == ["Frank Herbert", "Brian Herbert"]


def test_corrupt_epub_is_rejected(tmp_path: Path):
    path = tmp_path / "broken.epub"
    path.write_text("this is not a zip file", encoding="utf-8")
    with pytest.raises(metadata.InvalidFile):
        metadata.read_epub(path)


def test_zip_without_opf_is_rejected(tmp_path: Path):
    import zipfile

    path = tmp_path / "broken.epub"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
    with pytest.raises(metadata.InvalidFile):
        metadata.read_epub(path)


def test_read_mp3_metadata(tmp_path: Path):
    path = generate_mp3(
        tmp_path / "book.mp3",
        title="Dune",
        artist="Frank Herbert",
        narrator="Simon Vance",
        track=4,
        cover=make_cover(),
    )
    found = metadata.read_audio(path)
    assert found["title"] == "Dune"
    assert found["authors"] == ["Frank Herbert"]
    assert found["narrator"] == "Simon Vance"
    assert found["track"] == 4
    assert found["duration"] > 0
    assert found["cover"]


def test_read_m4a_metadata(tmp_path: Path):
    path = generate_m4a(
        tmp_path / "book.m4a",
        title="Dune",
        artist="Frank Herbert",
        narrator="Simon Vance",
        track=2,
        seconds=90,
        cover=make_cover(),
    )
    found = metadata.read_audio(path)
    assert found["title"] == "Dune"
    assert found["authors"] == ["Frank Herbert"]
    assert found["narrator"] == "Simon Vance"
    assert found["track"] == 2
    assert abs(found["duration"] - 90) < 0.5
    assert found["cover"]


def test_junk_tags_are_empty(tmp_path: Path):
    path = generate_mp3(
        tmp_path / "junk.mp3", title="Track 01", artist="Unknown Artist", narrator="Unknown"
    )
    found = metadata.read_audio(path)
    assert found["title"] == ""
    assert found["authors"] == []
    assert found["narrator"] == ""


def test_unreadable_audio_is_rejected(tmp_path: Path):
    path = tmp_path / "broken.mp3"
    path.write_text("not an mp3", encoding="utf-8")
    with pytest.raises(metadata.InvalidFile):
        metadata.read_audio(path)


def test_folder_audiobook_uses_track_order_and_sums_duration(tmp_path: Path):
    folder = tmp_path / "audio"
    folder.mkdir()
    generate_mp3(folder / "a.mp3", title="Second", track=2, frames=40)
    generate_mp3(folder / "b.mp3", title="First", track=1, frames=60)
    found = metadata.read_audio_folder(folder)
    assert found["title"] == "First"
    assert [entry["path"].name for entry in found["entries"]] == ["b.mp3", "a.mp3"]
    assert found["duration"] > 1.5


def test_folder_audiobook_falls_back_to_natural_names(tmp_path: Path):
    folder = tmp_path / "audio"
    folder.mkdir()
    generate_mp3(folder / "chapter 10.mp3", title="Ten", track=None)
    generate_mp3(folder / "chapter 2.mp3", title="Two", track=None)
    found = metadata.read_audio_folder(folder)
    assert found["title"] == "Two"
    assert [entry["path"].name for entry in found["entries"]] == [
        "chapter 2.mp3",
        "chapter 10.mp3",
    ]


def test_folder_audiobook_with_bad_file_fails(tmp_path: Path):
    folder = tmp_path / "audio"
    folder.mkdir()
    generate_mp3(folder / "good.mp3", title="Good")
    (folder / "bad.mp3").write_text("not audio", encoding="utf-8")
    with pytest.raises(metadata.InvalidFile):
        metadata.read_audio_folder(folder)


def test_folder_audiobook_with_no_audio_fails(tmp_path: Path):
    folder = tmp_path / "audio"
    folder.mkdir()
    (folder / "notes.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(metadata.InvalidFile):
        metadata.read_audio_folder(folder)
