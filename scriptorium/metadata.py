# EPUB and audio tag readers. Only values actually present in tags are
# returned; obvious junk values are treated as empty.
from __future__ import annotations

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

import mutagen
import mutagen.mp3
import mutagen.mp4

from .naming import collapse
from .textutil import clean_series_number

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".m4b"}
EBOOK_EXTENSIONS = {".epub"}
JUNK_VALUES = {
    "unknown",
    "unknown artist",
    "unknown author",
    "unknown narrator",
    "various",
    "various artists",
    "untitled",
    "track",
}


class InvalidFile(Exception):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append(" ")


def _strip_markup(text: str) -> str:
    if not text:
        return ""
    if "<" not in text:
        return collapse(text)
    parser = _TextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return collapse(text)
    return collapse(" ".join(parser.parts))


def clean_tag(value) -> str:
    text = collapse(value)
    if not text:
        return ""
    key = text.casefold()
    if key in JUNK_VALUES:
        return ""
    if re.fullmatch(r"(track|chapter)\s*0*\d+", key):
        return ""
    return text


def _unique(values) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = clean_tag(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _local(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _attr(element, name: str) -> str:
    for key, value in element.attrib.items():
        if key.rsplit("}", 1)[-1] == name:
            return value
    return ""


def _children(element, name: str):
    if element is None:
        return []
    return [child for child in element if _local(child) == name]


def _first(element, name: str):
    found = _children(element, name)
    return found[0] if found else None


def _text(element) -> str:
    return collapse("".join(element.itertext())) if element is not None else ""


def _container_path(archive: zipfile.ZipFile) -> str:
    try:
        data = archive.read("META-INF/container.xml")
    except KeyError:
        raise InvalidFile("this file is not a readable EPUB")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise InvalidFile("this file is not a readable EPUB")
    for element in root.iter():
        if _local(element) == "rootfile" and element.get("full-path"):
            return element.get("full-path")
    raise InvalidFile("this file is not a readable EPUB")


def _archive_member(opf_directory: str, href: str) -> str:
    cleaned = unquote(href.split("#", 1)[0])
    return posixpath.normpath(posixpath.join(opf_directory, cleaned))


def _epub_cover(archive: zipfile.ZipFile, root, opf_directory: str) -> bytes | None:
    manifest = _first(root, "manifest")
    items = _children(manifest, "item")
    cover_id = ""
    for element in root.iter():
        if _local(element) == "meta" and (element.get("name") or "").casefold() == "cover":
            cover_id = element.get("content") or ""
    chosen = None
    for item in items:
        if cover_id and item.get("id") == cover_id:
            chosen = item
            break
    if chosen is None:
        for item in items:
            properties = (item.get("properties") or "").split()
            if "cover-image" in properties:
                chosen = item
                break
    if chosen is None:
        return None
    href = chosen.get("href") or ""
    if not href or "://" in href:
        return None
    try:
        return archive.read(_archive_member(opf_directory, href))
    except (KeyError, OSError):
        return None


def read_epub(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            opf_path = _container_path(archive)
            try:
                opf_data = archive.read(opf_path)
            except KeyError:
                raise InvalidFile("this file is not a readable EPUB")
            try:
                root = ET.fromstring(opf_data)
            except ET.ParseError:
                raise InvalidFile("this file is not a readable EPUB")
            metadata = _first(root, "metadata")
            title = ""
            creators = []
            description = ""
            series = ""
            series_number = ""
            for element in list(metadata) if metadata is not None else []:
                name = _local(element)
                if name == "title" and not title:
                    title = clean_tag(_text(element))
                elif name == "creator":
                    creators.append(element)
                elif name == "description" and not description:
                    description = _strip_markup(_text(element))
                elif name == "meta":
                    meta_name = (element.get("name") or "").casefold()
                    property_name = (element.get("property") or "").casefold()
                    if meta_name == "calibre:series":
                        series = clean_tag(element.get("content"))
                    elif meta_name == "calibre:series_index":
                        series_number = clean_series_number(element.get("content"))
                    elif property_name == "belongs-to-collection" and not series:
                        series = clean_tag(_text(element))
                    elif property_name == "group-position" and not series_number:
                        series_number = clean_series_number(_text(element))
            primary = [item for item in creators if _attr(item, "role") == "aut"]
            chosen = primary or creators
            authors = _unique(_text(item) for item in chosen)
            cover = _epub_cover(archive, root, posixpath.dirname(opf_path))
    except InvalidFile:
        raise
    except (zipfile.BadZipFile, OSError, ET.ParseError, ValueError, RuntimeError):
        raise InvalidFile("this file is not a readable EPUB")
    return {
        "title": title,
        "authors": authors,
        "narrator": "",
        "description": description,
        "series": series,
        "series_number": series_number,
        "duration": 0.0,
        "cover": cover,
        "track": None,
    }


def _id3_text(tags, key: str) -> str:
    if tags is None:
        return ""
    frame = tags.get(key)
    values = getattr(frame, "text", None) if frame is not None else None
    if not values:
        return ""
    return clean_tag(values[0])


def _id3_values(tags, key: str) -> list[str]:
    if tags is None:
        return []
    frame = tags.get(key)
    values = getattr(frame, "text", None) if frame is not None else None
    return _unique(values or [])


def _id3_person(tags, kind: str) -> str:
    wanted = {kind, "narrator", "reader", "narrated by"}
    if tags is not None:
        for frame in tags.getall("TXXX"):
            if (frame.desc or "").casefold() in wanted and frame.text:
                return clean_tag(frame.text[0])
    return ""


def _id3_cover(tags) -> bytes | None:
    if tags is None:
        return None
    frames = tags.getall("APIC")
    if not frames:
        return None
    for frame in frames:
        if getattr(frame, "type", 0) == 3:
            return frame.data
    return frames[0].data


def _track_number(value) -> int | None:
    text = collapse(value)
    if not text:
        return None
    head = text.split("/", 1)[0].strip()
    try:
        number = int(head)
    except ValueError:
        return None
    return number if number > 0 else None


def _read_mp3(audio) -> dict:
    tags = audio.tags
    title = _id3_text(tags, "TIT2")
    authors = _id3_values(tags, "TPE1") or _id3_values(tags, "TPE2")
    narrator = _id3_person(tags, "narrator") or _id3_text(tags, "TCOM")
    cover = _id3_cover(tags)
    return {
        "title": title,
        "authors": authors,
        "narrator": narrator,
        "description": "",
        "series": "",
        "series_number": "",
        "duration": float(getattr(audio.info, "length", 0) or 0),
        "cover": cover,
        "track": _track_number(_id3_text(tags, "TRCK")),
    }


def _mp4_text(tags, key: str) -> str:
    value = tags.get(key)
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    return clean_tag(value)


def _mp4_authors(tags) -> list[str]:
    values = tags.get("\xa9ART") or tags.get("aART") or []
    if isinstance(values, str):
        values = [values]
    return _unique(values)


def _mp4_freeform(tags, name: str) -> str:
    value = tags.get(f"----:com.apple.iTunes:{name}")
    if isinstance(value, list):
        value = value[0] if value else b""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    return clean_tag(value)


def _mp4_cover(tags) -> bytes | None:
    covers = tags.get("covr") or []
    if not covers:
        return None
    return bytes(covers[0])


def _mp4_track(tags) -> int | None:
    values = tags.get("trkn") or []
    if not values:
        return None
    pair = values[0]
    if isinstance(pair, (tuple, list)) and pair:
        number = int(pair[0])
        return number if number > 0 else None
    return None


def _read_mp4(audio) -> dict:
    tags = audio.tags or {}
    title = _mp4_text(tags, "\xa9nam")
    authors = _mp4_authors(tags)
    narrator = _mp4_freeform(tags, "NARRATOR") or _mp4_text(tags, "\xa9wrt")
    return {
        "title": title,
        "authors": authors,
        "narrator": narrator,
        "description": "",
        "series": "",
        "series_number": "",
        "duration": float(getattr(audio.info, "length", 0) or 0),
        "cover": _mp4_cover(tags),
        "track": _mp4_track(tags),
    }


def read_audio(path: Path) -> dict:
    try:
        audio = mutagen.File(str(path))
    except Exception:
        raise InvalidFile("this file is not a readable audio file")
    if audio is None or getattr(audio, "info", None) is None:
        raise InvalidFile("this file is not a readable audio file")
    if isinstance(audio, mutagen.mp3.MP3):
        return _read_mp3(audio)
    if isinstance(audio, mutagen.mp4.MP4):
        return _read_mp4(audio)
    if path.suffix.lower() == ".mp3":
        return _read_mp3(audio)
    return _read_mp4(audio)


def natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


def read_audio_folder(folder: Path) -> dict:
    entries = []
    for item in folder.iterdir():
        if not item.is_file() or item.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            metadata = read_audio(item)
        except InvalidFile:
            raise InvalidFile(f"'{item.name}' is not a readable audio file")
        entries.append(
            {
                "path": item,
                "track": metadata["track"],
                "duration": metadata["duration"],
                "metadata": metadata,
            }
        )
    if not entries:
        raise InvalidFile("this folder has no audio files")
    entries.sort(
        key=lambda entry: (
            0 if entry["track"] else 1,
            entry["track"] or 0,
            natural_key(entry["path"].name),
        )
    )
    first = entries[0]["metadata"]
    return {
        "title": first["title"],
        "authors": first["authors"],
        "narrator": first["narrator"],
        "description": "",
        "series": "",
        "series_number": "",
        "duration": sum(entry["duration"] for entry in entries),
        "cover": first["cover"],
        "track": None,
        "entries": entries,
    }
