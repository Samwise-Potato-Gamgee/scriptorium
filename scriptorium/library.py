# Library folder handling: opening, creating, folder structure,
# database backups, staging areas and safe relative paths.
from __future__ import annotations

import datetime as dt
import os
import shutil
from pathlib import Path

from . import db

RESERVED_DIRECTORIES = ("covers", "thumbnails", "backups", "trash")
STAGING_DIRECTORY = ".staging"
MAX_BACKUPS = 5


class LibraryError(Exception):
    pass


class Library:
    def __init__(self, root):
        self.root = Path(root).expanduser().absolute()

    @property
    def db_path(self) -> Path:
        return self.root / "library.db"

    @classmethod
    def open(cls, root) -> "Library":
        library = cls(root)
        if not library.root.is_dir():
            raise LibraryError("library folder not found at this path")
        if not library.db_path.is_file():
            raise LibraryError("no library found at this path")
        library.ensure_structure()
        return library

    @classmethod
    def create(cls, root) -> "Library":
        library = cls(root)
        try:
            library.root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise LibraryError(f"the library folder could not be created: {error}")
        if not library.root.is_dir():
            raise LibraryError("the library path is not a folder")
        library.ensure_structure()
        with db.session(library.db_path) as connection:
            db.init_schema(connection)
        return library

    def ensure_structure(self) -> None:
        for name in RESERVED_DIRECTORIES:
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / STAGING_DIRECTORY).mkdir(parents=True, exist_ok=True)

    def cleanup_staging(self) -> None:
        staging = self.root / STAGING_DIRECTORY
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)

    def backup(self) -> Path | None:
        if not self.db_path.is_file():
            return None
        backups = self.root / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = backups / f"library-{stamp}.db"
        temporary = destination.with_name(destination.name + ".tmp")
        shutil.copy2(self.db_path, temporary)
        os.replace(temporary, destination)
        files = sorted(
            (path for path in backups.iterdir() if path.is_file() and path.suffix == ".db"),
            key=lambda path: path.name,
        )
        for old in files[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except OSError:
                pass
        return destination

    def backup_list(self) -> list[dict]:
        backups = self.root / "backups"
        if not backups.is_dir():
            return []
        items = []
        for path in sorted(backups.iterdir(), key=lambda item: item.name, reverse=True):
            if path.is_file() and path.suffix == ".db":
                try:
                    stat = path.stat()
                except OSError:
                    continue
                items.append(
                    {"name": path.name, "size": stat.st_size, "modified": stat.st_mtime}
                )
        return items

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def path(self, relative: str) -> Path:
        if not relative:
            raise LibraryError("missing stored path")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise LibraryError("stored path is outside the library")
        return self.root.joinpath(*candidate.parts)

    def staging(self) -> Path:
        stage = self.root / STAGING_DIRECTORY / dt.datetime.now().strftime("%Y%m%d%H%M%S%f")
        stage.mkdir(parents=True, exist_ok=False)
        return stage

    def cover_path(self, name: str) -> Path:
        return self.root / "covers" / name

    def thumbnail_path(self, name: str) -> Path:
        return self.root / "thumbnails" / name

    def trash_path(self, name: str = "") -> Path:
        base = self.root / "trash"
        return base / name if name else base
