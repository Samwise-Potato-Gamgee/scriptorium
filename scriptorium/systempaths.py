# The only OS-specific module: config location, default library parent,
# opening the browser and hidden subprocess flags.
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def config_directory() -> Path:
    override = os.environ.get("SCRIPTORIUM_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / "Scriptorium"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Scriptorium"
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "scriptorium"


def default_library_parent() -> Path:
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        pass


def hidden_process_flags() -> int:
    if sys.platform.startswith("win"):
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0
