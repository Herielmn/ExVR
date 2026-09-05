from __future__ import annotations

import threading
from typing import Any, Callable

_lock = threading.RLock()
_commands: dict[str, Callable[..., Any]] = {}
_queries: dict[str, Callable[[], Any]] = {}
_descriptions: dict[str, str] = {}


def register(name: str, handler: Callable[..., Any], description: str = "") -> None:
    with _lock:
        _commands[name] = handler
        _descriptions[name] = description or (handler.__doc__ or "").strip().split("\n")[0]


def register_query(name: str, handler: Callable[[], Any]) -> None:
    with _lock:
        _queries[name] = handler


def unregister(name: str) -> None:
    with _lock:
        _commands.pop(name, None)
        _descriptions.pop(name, None)


def clear() -> None:
    with _lock:
        _commands.clear()
        _queries.clear()
        _descriptions.clear()


def names() -> dict[str, str]:
    with _lock:
        return dict(sorted(_descriptions.items()))


def invoke(name: str, **kwargs) -> Any:
    with _lock:
        handler = _commands[name]
    return handler(**kwargs)


def query(name: str, default=None) -> Any:
    with _lock:
        handler = _queries.get(name)
    if handler is None:
        return default
    try:
        return handler()
    except Exception as exc:
        print(f"[api] query {name!r} raised: {exc}")
        return default
