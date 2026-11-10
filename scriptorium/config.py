# Per-machine settings stored as JSON in the config directory, with an
# environment override for development and tests.
from __future__ import annotations

import json
import os
from pathlib import Path

from . import systempaths

DEFAULTS = {
    "library_path": "",
    "port": 8737,
    "accent": "#e0a13a",
    "theme": "system",
    "delete_originals": False,
}


def config_path() -> Path:
    return systempaths.config_directory() / "config.json"


def load() -> dict:
    data = dict(DEFAULTS)
    path = config_path()
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    if isinstance(stored, dict):
        for key in DEFAULTS:
            if key in stored:
                data[key] = stored[key]
    return data


def save(data: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: data.get(key, DEFAULTS[key]) for key in DEFAULTS}
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, path)


def update(**values) -> dict:
    data = load()
    for key, value in values.items():
        if key in DEFAULTS:
            data[key] = value
    save(data)
    return data
