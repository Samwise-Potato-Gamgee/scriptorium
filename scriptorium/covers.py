# Cover storage: normalises embedded or uploaded images to JPEG and
# generates thumbnails, plus small previews for the review screen.
from __future__ import annotations

import base64
import io
import os
import uuid

from PIL import Image, ImageOps

from .library import Library


class CoverError(Exception):
    pass


def _flatten(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        converted = image.convert("RGBA")
        background = Image.new("RGB", converted.size, (255, 255, 255))
        background.paste(converted, mask=converted.getchannel("A"))
        return background
    return image.convert("RGB")


def _fit(image: Image.Image, longest: int) -> Image.Image:
    if max(image.size) <= longest:
        return image
    copy = image.copy()
    copy.thumbnail((longest, longest), Image.LANCZOS)
    return copy


def _write_jpeg(image: Image.Image, target, quality: int) -> None:
    temporary = target.with_name(target.name + ".tmp")
    image.save(temporary, format="JPEG", quality=quality, optimize=True)
    os.replace(temporary, target)


def save(library: Library, data: bytes) -> tuple[str, str]:
    try:
        source = Image.open(io.BytesIO(data))
        source.load()
    except Exception:
        raise CoverError("this image could not be read")
    try:
        image = _flatten(ImageOps.exif_transpose(source))
    except Exception:
        raise CoverError("this image could not be read")
    name = f"{uuid.uuid4().hex}.jpg"
    full = library.cover_path(name)
    thumbnail = library.thumbnail_path(name)
    try:
        _write_jpeg(_fit(image, 1400), full, 88)
        _write_jpeg(_fit(image, 360), thumbnail, 82)
    except Exception:
        remove(library, name)
        raise CoverError("this image could not be saved")
    return name, name


def remove(library: Library, name: str) -> None:
    if not name:
        return
    for path in (library.cover_path(name), library.thumbnail_path(name)):
        try:
            path.unlink()
        except OSError:
            pass


def preview_data_url(data: bytes, longest: int = 320) -> str:
    if not data:
        return ""
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = _fit(_flatten(ImageOps.exif_transpose(image)), longest)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82)
    except Exception:
        return ""
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
