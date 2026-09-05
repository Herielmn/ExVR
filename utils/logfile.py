from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from utils.paths import app_path

LOG_DIR = ("settings", "logs")
LOG_NAME = "exvr.log"
MAX_BYTES = 2_000_000
KEEP = 1

_lock = threading.Lock()
_installed = False

_secrets: list[str] = []


def add_secret(value: str) -> None:
    if value and value not in _secrets:
        _secrets.append(value)


def _scrub(text: str) -> str:
    for secret in _secrets:
        if secret in text:
            text = text.replace(secret, "<redacted>")
    return text


def console(stream: str = "stdout"):
    original = sys.__stdout__ if stream == "stdout" else sys.__stderr__
    return original if original is not None else getattr(sys, stream)


def log_path() -> Path:
    return app_path(*LOG_DIR) / LOG_NAME


class _Tee:

    def __init__(self, stream, path: Path, label: str):
        self._stream = stream
        self._path = path
        self._label = label
        self._at_line_start = True

    def write(self, text):
        if self._stream is not None:
            try:
                self._stream.write(text)
            except Exception:
                pass
        if text:
            self._append(text)
        return len(text)

    def _append(self, text):
        text = _scrub(text)
        stamped = []
        for piece in text.splitlines(keepends=True):
            if self._at_line_start and piece.strip():
                stamped.append(f"{time.strftime('%H:%M:%S')} {self._label} {piece}")
            else:
                stamped.append(piece)
            self._at_line_start = piece.endswith(("\n", "\r"))
        payload = "".join(stamped).encode("utf-8", "replace")
        with _lock:
            try:
                _rotate_if_needed(self._path, len(payload))
                with open(self._path, "ab") as handle:
                    handle.write(payload)
            except OSError:
                pass

    def flush(self):
        if self._stream is not None:
            try:
                self._stream.flush()
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _rotate_if_needed(path: Path, incoming: int) -> None:
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size + incoming <= MAX_BYTES:
        return
    previous = path.with_suffix(path.suffix + ".1")
    try:
        if previous.exists():
            previous.unlink()
        path.rename(previous)
    except OSError:
        pass


def start_fresh() -> None:
    path = log_path()
    with _lock:
        for target in (path, path.with_suffix(path.suffix + ".1")):
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                try:
                    with open(target, "wb"):
                        pass
                except OSError:
                    pass


def install() -> Path:
    global _installed
    path = log_path()
    if _installed:
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return path
    _installed = True
    sys.stdout = _Tee(sys.stdout, path, "out")
    sys.stderr = _Tee(sys.stderr, path, "err")
    return path


def tail(limit_bytes: int = 200_000) -> str:
    path = log_path()
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - limit_bytes))
            data = handle.read()
    except OSError:
        return ""
    if size > limit_bytes:
        data = data.split(b"\n", 1)[-1]
    return data.decode("utf-8", "replace")
