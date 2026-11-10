# Server startup: single-instance detection, opening the browser and
# running uvicorn on the loopback interface only.
from __future__ import annotations

import threading
import urllib.error
import urllib.request

import uvicorn

from . import systempaths
from .api import create_app


def is_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/state", timeout=0.7
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def run(port: int, open_browser: bool = True) -> int:
    url = f"http://127.0.0.1:{port}/"
    if is_running(port):
        print(f"Scriptorium is already running at {url}")
        if open_browser:
            systempaths.open_browser(url)
        return 0
    application = create_app()
    if open_browser:
        timer = threading.Timer(0.9, systempaths.open_browser, args=(url,))
        timer.daemon = True
        timer.start()
    uvicorn.run(application, host="127.0.0.1", port=port, log_level="info")
    return 0
