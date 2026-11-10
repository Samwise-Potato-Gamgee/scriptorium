# Tests for the native dialog runner: one dialog at a time, cancel and errors.
from __future__ import annotations

import threading

import pytest

from scriptorium import dialogs


def test_choose_returns_the_picked_path(monkeypatch):
    monkeypatch.setattr(dialogs, "_ask", lambda kind, start: "/tmp/book.epub")
    assert dialogs.choose("file") == "/tmp/book.epub"


def test_cancel_returns_an_empty_path(monkeypatch):
    monkeypatch.setattr(dialogs, "_ask", lambda kind, start: "")
    assert dialogs.choose("folder") == ""


def test_unavailable_dialog_reports_an_error(monkeypatch):
    def fail(kind, start):
        raise dialogs.DialogUnavailable("the system dialog is not available")

    monkeypatch.setattr(dialogs, "_ask", fail)
    with pytest.raises(dialogs.DialogUnavailable):
        dialogs.choose("file")
    assert not dialogs._busy.locked()


def test_unknown_kind_is_rejected():
    with pytest.raises(dialogs.DialogUnavailable):
        dialogs.choose("something")


def test_only_one_dialog_at_a_time(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow(kind, start):
        started.set()
        release.wait(5)
        return "/tmp/chosen"

    monkeypatch.setattr(dialogs, "_ask", slow)
    result = {}
    thread = threading.Thread(
        target=lambda: result.update(path=dialogs.choose("file"))
    )
    thread.start()
    try:
        assert started.wait(5)
        with pytest.raises(dialogs.DialogBusy):
            dialogs.choose("folder")
    finally:
        release.set()
    thread.join(5)
    assert result["path"] == "/tmp/chosen"
    assert not dialogs._busy.locked()
