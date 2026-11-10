# Scriptorium

Scriptorium is a local, offline library manager for EPUB ebooks and MP3, M4A and M4B audiobooks. It runs as a small web server on your own computer and is used in the browser. Each machine has its own independent library; nothing is synced.

## Features

- One book entry with an ebook edition, an audiobook edition, or both.
- Safe import by file or folder path: the copy is verified by size and SHA-256 checksum before the database entry is saved and the original is deleted. A per-import checkbox (and a setting) can keep the original instead.
- Native **Choose file…** / **Choose folder…** buttons next to every path field open the operating system's dialog; pasting a path still works.
- EPUB metadata: title, authors, cover, description, series name and number.
- Audio metadata: title, author, narrator, cover and duration; folder audiobooks keep their play order and sum the duration of every file.
- A review screen before importing through the app; a direct import command for the terminal.
- Likely-duplicate warning with the choice to attach a second edition or create a separate entry.
- Cover grid and sortable table with endless scrolling, search, and filters for genre, subgenre, status, format and needs-review.
- Home page with recently added and unread rows plus library counts.
- Series page with reading order and missing numbers.
- Book page with both editions, durations, folder-audiobook file counts, covers, replace-file and remove-edition actions.
- Editing, bulk editing, cover uploads and narrator editing.
- Trash with restore for deleted books and editions, a read-only library check, and automatic database backups.
- Light and dark themes, eight accent colours plus a custom picker, bundled Inter font and inline SVG icons. No network access is ever made by the app.
- Responsive layout for desktop and phone-sized browser windows.

## Requirements

- [Miniconda or Anaconda](https://docs.conda.io/) to create the environment.
- No other system programs are required: no Node.js, no build step, no ffmpeg. The native file and folder dialogs use Tk, which ships with the Python in the environment.

## One-time setup

From the project folder:

```bash
conda env create -p ./env -f environment.yml
conda activate ./env
```

On Windows, activate with `conda activate .\env`. You can also call the environment's Python directly, for example `./env/bin/python` (Linux/macOS) or `.\env\Scripts\python.exe` (Windows).

The app uses only `fastapi`, `uvicorn`, `mutagen`, `Pillow` and `pytest`, plus the standard library. The environment is created as a prefix environment inside this folder at `./env`.

## Launch

```bash
python -m scriptorium
```

The server listens on `127.0.0.1` and opens your browser. Press `Ctrl+C` in the terminal to stop it. If Scriptorium is already running on the configured port, a second launch simply opens the browser to the running copy.

Useful options:

```bash
python -m scriptorium --library /path/to/library --port 8737
python -m scriptorium --no-browser
```

On the first start, choose the library folder in the browser. The folder is opened if it already contains a library, or you are asked before a new empty library is created there. The library folder should live outside this project folder. If the folder is missing later (for example an unplugged drive), the app shows a "library folder not found" screen with Retry and a folder field; it never creates a new library automatically.

## Adding books

In the app, use **Add book**, then paste a file or folder path (or click **Choose file…** / **Choose folder…** to pick it in the operating system's dialog), and choose **Read file**. The file is read where it sits; nothing is uploaded. Review the metadata, correct anything that is blank or wrong, and import.

The review screen has a **Delete the original after import** checkbox, unticked by default. Ticked, the source is removed once the library copy is verified. Unticked, the copy is still verified and saved, but the source file or folder stays where it is. For folder audiobooks the choice applies to the whole folder; stray non-audio files are left alone either way. The Replace file dialog has the same checkbox and only affects the new source; the old library file always goes to the trash.

The starting state of that checkbox comes from **Settings → Importing → Delete originals after import by default**, which is off until you turn it on.

The command line imports directly without a review screen:

```bash
python -m scriptorium add /path/to/book.epub
python -m scriptorium add /path/to/audiobook-folder
python -m scriptorium add /path/to/book.epub --keep-original
```

The command line imports use only the tags. Because genre is always a user choice and is never taken from tags, those imports are flagged **Needs review**; the flag can be cleared in the edit form. A book with no title in its tags is skipped and its original file is left untouched. Likely duplicates are also skipped and reported. `--keep-original` leaves the source file or folder in place after the verified copy is saved; without it the original is deleted as before.

## Where things live

The library folder that you choose contains:

```
library.db
covers/       full-size covers
thumbnails/   small cover thumbnails
backups/      the last five copies of library.db
trash/        deleted books, editions and replaced files with their metadata
<First Author>/<Title>/
```

Per-machine settings (library folder, port, theme, accent and whether originals are deleted after import) are stored outside the library:

- Linux: `~/.config/scriptorium/config.json`
- macOS: `~/Library/Application Support/Scriptorium/config.json`
- Windows: `%APPDATA%\Scriptorium\config.json`

For development or tests you can override this location with the `SCRIPTORIUM_CONFIG_DIR` environment variable. The library folder is opened or created explicitly; changing it in Settings never moves files between libraries. A port change takes effect after restarting the app.

## Safety

The import sequence is always: read and validate → copy → verify size and checksum → save the database entry → delete the original (unless you asked to keep it). If anything fails, the original is left in place and no half-imported entry remains. A folder audiobook is imported as one unit. Replaced files and deleted books or editions go to the trash and can be restored until you empty it. `library.db` is backed up at each start, with the last five backups kept.

## Tests

```bash
python -m pytest
```

The tests use temporary folders and generate tiny valid EPUB, MP3 and M4A/M4B files in code. They never touch a real library. They cover import failures, checksum verification, keeping originals, folder audiobooks, name shortening and clashes, renaming, replacement, trash and restore, duplicate detection, the native dialog runner and the library check.

## Bundled font

Inter is included as a variable woff2 under `scriptorium/static/fonts/`, together with its SIL Open Font License in `scriptorium/static/fonts/OFL.txt`. Icons are inline SVG in `scriptorium/static/js/icons.js`. The app makes no external requests.
