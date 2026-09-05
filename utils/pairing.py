from __future__ import annotations

import hmac
import json
import secrets
import threading
import time

from utils.json_manager import save_json
from utils.paths import app_path

STORE = "settings/pairing.json"

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
TOKEN_LENGTH = 8

QUERY_KEY = "k"
COOKIE_NAME = "exvr_pair"

FAILURES_BEFORE_LOCKOUT = 5
FIRST_LOCKOUT_SECONDS = 30.0
MAX_LOCKOUT_SECONDS = 900.0
FAILURE_WINDOW_SECONDS = 600.0

_lock = threading.Lock()
_token: str | None = None


def _new_token() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(TOKEN_LENGTH))


def _read_stored() -> str | None:
    try:
        with app_path(STORE).open(encoding="utf-8") as fh:
            stored = json.load(fh).get("token")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(stored, str) and len(stored) == TOKEN_LENGTH:
        return stored
    return None


def get_or_create_token() -> str:
    global _token
    with _lock:
        if _token is not None:
            return _token
        _token = _read_stored()
        if _token is None:
            _token = _new_token()
            save_json({"token": _token}, STORE)
        return _token


def rotate_token() -> str:
    global _token
    with _lock:
        _token = _new_token()
        save_json({"token": _token}, STORE)
    _throttle.clear()
    return _token


def normalise(candidate: str | None) -> str:
    if not candidate:
        return ""
    folded = candidate.strip().upper().replace(" ", "").replace("-", "")
    return folded.translate(str.maketrans("ILOU", "110V"))


def matches(candidate: str | None) -> bool:
    supplied = normalise(candidate)
    if len(supplied) != TOKEN_LENGTH:
        return False
    return hmac.compare_digest(supplied, get_or_create_token())


class Throttle:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, float, float]] = {}

    def locked_for(self, address: str) -> float:
        with self._lock:
            entry = self._state.get(address)
            if entry is None:
                return 0.0
            _fails, _last, until = entry
            return max(0.0, until - time.monotonic())

    def record_failure(self, address: str) -> float:
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            fails, last, until = self._state.get(address, (0, now, 0.0))
            if now - last > FAILURE_WINDOW_SECONDS:
                fails = 0
            fails += 1
            if fails >= FAILURES_BEFORE_LOCKOUT:
                over = fails - FAILURES_BEFORE_LOCKOUT
                lockout = min(FIRST_LOCKOUT_SECONDS * (2 ** over), MAX_LOCKOUT_SECONDS)
                until = now + lockout
            self._state[address] = (fails, now, until)
            return max(0.0, until - now)

    def record_success(self, address: str) -> None:
        with self._lock:
            self._state.pop(address, None)

    def clear(self) -> None:
        with self._lock:
            self._state.clear()

    def _evict(self, now: float) -> None:
        if len(self._state) < 1024:
            return
        stale = [key for key, (_f, last, until) in self._state.items()
                 if now - last > FAILURE_WINDOW_SECONDS and until <= now]
        for key in stale:
            del self._state[key]


_throttle = Throttle()


def throttle() -> Throttle:
    return _throttle
