# Native file and folder pickers: opens the operating system dialog with
# tkinter in a separate Python process so the server never blocks, and
# allows only one dialog at a time.
from __future__ import annotations

import importlib.util
import subprocess
import sys
import threading
from pathlib import Path

from . import systempaths

FILE_TYPES = [
    ("Books and audio", "*.epub *.mp3 *.m4a *.m4b"),
    ("EPUB", "*.epub"),
    ("MP3", "*.mp3"),
    ("M4A", "*.m4a"),
    ("M4B", "*.m4b"),
    ("All files", "*.*"),
]
KINDS = {"file", "folder"}
WAIT_SECONDS = 1800.0

_busy = threading.Lock()

_CHILD = """
import sys
import tkinter
from tkinter import filedialog
filetypes = __FILETYPES__
kind = sys.argv[1]
start = sys.argv[2] or None
try:
    root = tkinter.Tk()
except Exception as error:
    print("ERROR: " + str(error), file=sys.stderr)
    raise SystemExit(2)
try:
    root.withdraw()
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.lift()
    root.focus_force()

    def keep_on_top():
        try:
            for window in root.tk.call("winfo", "children", "."):
                root.tk.call("wm", "attributes", window, "-topmost", True)
        except Exception:
            pass
        try:
            root.after(200, keep_on_top)
        except Exception:
            pass

    root.after(200, keep_on_top)
    if kind == "folder":
        chosen = filedialog.askdirectory(
            parent=root, title="Choose folder", initialdir=start, mustexist=True
        )
    else:
        chosen = filedialog.askopenfilename(
            parent=root, title="Choose file", initialdir=start, filetypes=filetypes
        )
except Exception as error:
    print("ERROR: " + str(error), file=sys.stderr)
    raise SystemExit(3)
finally:
    try:
        root.destroy()
    except Exception:
        pass
sys.stdout.write(chosen or "")
sys.stdout.flush()
""".replace("__FILETYPES__", repr(FILE_TYPES))


class DialogUnavailable(Exception):
    pass


class DialogBusy(Exception):
    pass


# Returns a directory to start the dialog in, based on a typed path or folder.
def _start_directory(start: str) -> str:
    text = str(start or "").strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    try:
        if path.is_file():
            return str(path.parent)
        if path.is_dir():
            return str(path)
        if path.parent.is_dir():
            return str(path.parent)
    except OSError:
        return ""
    return ""


# Turns the child process error output into one short readable line.
def _error_text(stderr: str) -> str:
    for line in reversed(str(stderr or "").splitlines()):
        if line.startswith("ERROR: "):
            return line[7:].strip()
    for line in reversed(str(stderr or "").splitlines()):
        if line.strip():
            return line.strip()
    return "the dialog closed unexpectedly"


# Runs the tkinter dialog in a child process and returns the chosen path.
# kind is "file" or "folder"; start is the path or folder the field holds.
def _ask(kind: str, start: str) -> str:
    if importlib.util.find_spec("tkinter") is None:
        raise DialogUnavailable(
            "the system dialog is not available on this machine; paste the path instead"
        )
    command = [
        sys.executable,
        "-X",
        "utf8",
        "-c",
        _CHILD,
        kind,
        _start_directory(start),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=WAIT_SECONDS,
            creationflags=systempaths.hidden_process_flags(),
        )
    except OSError as error:
        raise DialogUnavailable(
            f"the system dialog could not start ({error}); paste the path instead"
        )
    except subprocess.TimeoutExpired:
        raise DialogUnavailable(
            "the system dialog did not return a choice; paste the path instead"
        )
    if completed.returncode == 0:
        return completed.stdout
    raise DialogUnavailable(
        f"the system dialog could not open ({_error_text(completed.stderr)}); paste the path instead"
    )


# Shows one native dialog and waits for the choice. Cancel returns "".
# kind is "file" or "folder"; start is the starting path; raises DialogBusy
# when another dialog is already open and DialogUnavailable when it cannot run.
def choose(kind: str, start: str = "") -> str:
    if kind not in KINDS:
        raise DialogUnavailable("the dialog kind must be 'file' or 'folder'")
    if not _busy.acquire(blocking=False):
        raise DialogBusy("a system dialog is already open")
    try:
        return _ask(kind, start)
    finally:
        _busy.release()
