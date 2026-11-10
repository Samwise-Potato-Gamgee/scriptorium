# Generators for tiny valid EPUB, MP3 and M4A/M4B files used by tests.
from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image


def make_cover(color=(60, 110, 160)) -> bytes:
    image = Image.new("RGB", (90, 135), color)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


def generate_epub(
    path: Path,
    title: str = "Dune",
    authors=("Frank Herbert",),
    series: str = "Dune",
    series_number: str = "1",
    description: str = "<p>A desert planet.</p>",
    cover: bool = True,
) -> Path:
    cover_data = make_cover() if cover else None
    creators = "".join(
        f'<dc:creator opf:role="aut">{escape(author)}</dc:creator>'
        for author in authors
    )
    series_meta = ""
    if series:
        series_meta += f'<meta name="calibre:series" content="{escape(series)}"/>'
    if series_number:
        series_meta += (
            f'<meta name="calibre:series_index" content="{escape(series_number)}"/>'
        )
    cover_meta = '<meta name="cover" content="cover"/>' if cover else ""
    cover_item = (
        '<item id="cover" href="cover.jpg" media-type="image/jpeg"/>' if cover else ""
    )
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{escape(title)}</dc:title>
    {creators}
    <dc:description>{escape(description)}</dc:description>
    {series_meta}
    {cover_meta}
  </metadata>
  <manifest>
    {cover_item}
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter"/>
  </spine>
</package>"""
    container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr(
            "OEBPS/chapter.xhtml",
            "<html><body><p>Chapter one.</p></body></html>",
        )
        if cover_data is not None:
            archive.writestr("OEBPS/cover.jpg", cover_data)
    return path


def generate_mp3(
    path: Path,
    title: str | None = "Test Audio",
    artist="Jane Doe",
    narrator: str = "John Reader",
    track: int | None = 1,
    frames: int = 40,
    cover: bytes | None = None,
) -> Path:
    from mutagen.id3 import APIC, TCOM, TIT2, TPE1, TRCK
    from mutagen.mp3 import MP3

    header = bytes.fromhex("FFFB9000")
    frame = header + b"\x00" * 413
    path.write_bytes(frame * frames)
    audio = MP3(str(path))
    audio.add_tags()
    tags = audio.tags
    if title is not None:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        values = [artist] if isinstance(artist, str) else list(artist)
        tags.add(TPE1(encoding=3, text=values))
    if narrator:
        tags.add(TCOM(encoding=3, text=narrator))
    if track is not None:
        tags.add(TRCK(encoding=3, text=str(track)))
    if cover is not None:
        tags.add(
            APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover)
        )
    audio.save()
    return path


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def _full_box(kind: bytes, version: int, flags: int, payload: bytes) -> bytes:
    return _box(kind, bytes([version]) + flags.to_bytes(3, "big") + payload)


def _data_atom(flags: int, payload: bytes) -> bytes:
    return _full_box(b"data", 0, flags, b"\x00\x00\x00\x00" + payload)


def _text_atom(key: bytes, text: str) -> bytes:
    return _box(key, _data_atom(1, text.encode("utf-8")))


def _descriptor(tag: int, payload: bytes) -> bytes:
    return bytes([tag, len(payload)]) + payload


def generate_m4a(
    path: Path,
    title: str = "Test Book",
    artist: str = "Jane Doe",
    narrator: str = "John Reader",
    track: int | None = 1,
    seconds: int = 60,
    cover: bytes | None = None,
) -> Path:
    ftyp = _box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2mp41")
    matrix = struct.pack(
        ">9I", 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000
    )
    mvhd = _full_box(
        b"mvhd",
        0,
        0,
        struct.pack(">IIII", 0, 0, 1000, seconds * 1000)
        + struct.pack(">I", 0x00010000)
        + struct.pack(">H", 0x0100)
        + b"\x00\x00"
        + b"\x00" * 8
        + matrix
        + b"\x00" * 24
        + struct.pack(">I", 2),
    )
    tkhd = _full_box(
        b"tkhd",
        0,
        7,
        struct.pack(">II", 0, 0)
        + struct.pack(">I", 1)
        + b"\x00" * 4
        + struct.pack(">I", seconds * 1000)
        + b"\x00" * 8
        + struct.pack(">HH", 0, 0)
        + struct.pack(">H", 0x0100)
        + b"\x00\x00"
        + matrix
        + struct.pack(">II", 0, 0),
    )
    mdhd = _full_box(
        b"mdhd",
        0,
        0,
        struct.pack(">II", 0, 0)
        + struct.pack(">II", 44100, 44100 * seconds)
        + struct.pack(">H", 0x55C4)
        + struct.pack(">H", 0),
    )
    hdlr = _full_box(
        b"hdlr", 0, 0, struct.pack(">I", 0) + b"soun" + b"\x00" * 12 + b"SoundHandler\x00"
    )
    smhd = _full_box(b"smhd", 0, 0, struct.pack(">HH", 0, 0))
    url = _full_box(b"url ", 0, 1, b"")
    dref = _full_box(b"dref", 0, 0, struct.pack(">I", 1) + url)
    dinf = _box(b"dinf", dref)
    dsi = _descriptor(0x05, b"\x12\x10")
    decoder_config = _descriptor(
        0x04,
        b"\x40\x15\x00\x00\x00" + struct.pack(">II", 128000, 128000) + dsi,
    )
    sl_config = _descriptor(0x06, b"\x02")
    es = _descriptor(
        0x03, struct.pack(">H", 1) + b"\x00" + decoder_config + sl_config
    )
    esds = _full_box(b"esds", 0, 0, es)
    sample_entry = (
        b"\x00" * 6
        + struct.pack(">H", 1)
        + b"\x00" * 8
        + struct.pack(">HH", 2, 16)
        + struct.pack(">HH", 0, 0)
        + struct.pack(">I", 44100 << 16)
        + esds
    )
    stsd = _full_box(b"stsd", 0, 0, struct.pack(">I", 1) + _box(b"mp4a", sample_entry))
    stbl = _box(b"stbl", stsd)
    minf = _box(b"minf", smhd + dinf + stbl)
    mdia = _box(b"mdia", mdhd + hdlr + minf)
    trak = _box(b"trak", tkhd + mdia)
    items = _text_atom(b"\xa9nam", title) + _text_atom(b"\xa9ART", artist)
    if narrator:
        items += _text_atom(b"\xa9wrt", narrator)
    if track is not None:
        items += _box(
            b"trkn",
            _data_atom(0, b"\x00\x00" + struct.pack(">HH", track, 10) + b"\x00\x00"),
        )
    if cover is not None:
        items += _box(b"covr", _data_atom(13, cover))
    ilst = _box(b"ilst", items)
    meta_hdlr = _full_box(
        b"hdlr", 0, 0, struct.pack(">I", 0) + b"mdir" + b"\x00" * 12 + b"\x00"
    )
    meta = _full_box(b"meta", 0, 0, meta_hdlr + ilst)
    moov = _box(b"moov", mvhd + trak + _box(b"udta", meta))
    mdat = _box(b"mdat", b"\x00" * 1024)
    path.write_bytes(ftyp + moov + mdat)
    return path
