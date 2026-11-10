# Tests for Windows-safe naming, shortening, clash suffixes and author sorting.
from __future__ import annotations

from pathlib import Path

from scriptorium import naming


def test_sanitize_replaces_only_forbidden_characters():
    assert naming.sanitize('A/B:C*D?E"F<G>H|I\\J') == "A B C D E F G H I J"
    assert naming.sanitize("Café — naïve") == "Café — naïve"


def test_sanitize_handles_trailing_dots_and_spaces():
    assert naming.sanitize("  A title.  ") == "A title"
    assert naming.sanitize("...") == "Untitled"
    assert naming.sanitize("") == "Untitled"


def test_sanitize_handles_windows_reserved_names():
    assert naming.sanitize("CON") == "CON_"
    assert naming.sanitize("nul") == "nul_"
    assert naming.sanitize("COM1") == "COM1_"


def test_sanitize_shortens_at_a_word_boundary():
    title = "A very long title " * 20
    cleaned = naming.sanitize(title)
    assert len(cleaned) <= naming.MAX_LENGTH
    assert not cleaned.endswith(" ")
    assert cleaned.startswith("A very long title")


def test_author_folder_reserved_and_missing():
    assert naming.author_folder("") == "Unknown"
    assert naming.author_folder("Covers") == "Covers (author)"
    assert naming.author_folder("Thumbnails") == "Thumbnails (author)"
    assert naming.author_folder("Frank Herbert") == "Frank Herbert"


def test_unique_entry_adds_number_suffix(tmp_path: Path):
    (tmp_path / "Dune").mkdir()
    assert naming.unique_entry(tmp_path, "Dune") == "Dune (2)"
    (tmp_path / "Dune (2)").mkdir()
    assert naming.unique_entry(tmp_path, "Dune") == "Dune (3)"


def test_unique_entry_can_ignore_itself(tmp_path: Path):
    (tmp_path / "Dune").mkdir()
    assert naming.unique_entry(tmp_path, "dune", ignore="Dune") == "dune"


def test_padding_width():
    assert naming.padding_width(1) == 2
    assert naming.padding_width(99) == 2
    assert naming.padding_width(100) == 3


def test_author_sort_uses_last_word():
    assert naming.author_sort_key("Frank Herbert") == "herbert frank"
    assert naming.author_sort_key("Ursula K. Le Guin") == "guin ursula k. le"
    assert naming.author_sort_key("") == ""


def test_last_first_conversion():
    assert naming.last_first_to_first_last("Herbert, Frank") == "Frank Herbert"
    assert naming.last_first_to_first_last("Herbert, Frank, Jr.") is None
    assert naming.last_first_to_first_last("Frank Herbert") is None


def test_free_path_keeps_current_name(tmp_path: Path):
    current = tmp_path / "Dune.epub"
    current.write_text("x", encoding="utf-8")
    assert naming.free_path(tmp_path, "Dune.epub", current) == current
    assert naming.free_path(tmp_path, "Dune.epub").name == "Dune (2).epub"
