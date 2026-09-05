from __future__ import annotations

import math
import threading
from typing import Any, Callable, Iterable

from utils.camera_presets import normalise_aspect, normalise_preset, resolution_for

RESTART_REQUIRED = frozenset({
    "config/Setting/camera_width",
    "config/Setting/camera_height",
    "config/Setting/camera_fps",
    "config/Setting/camera_ip",
    "config/Setting/camera_aspect",
    "config/Setting/camera_performance",
    "config/Sending/address",
    "config/Smoothing/enable",
    "config/Model/provider",
    "config/Model/Hand/model_complexity",
    "config/Controller/server_port",
    "config/Controller/websocket_port",
    "config/Controller/osc_port",
})

PORT_PATHS = ("Controller/server_port", "Controller/websocket_port",
              "Controller/osc_port")
PORT_LOW = 1024
PORT_HIGH = 65535

STICKY = ("Setting/language",)


class DeltaError(ValueError):

    def __init__(self, rejections: dict[str, str]):
        self.rejections = rejections
        detail = "; ".join(f"{path}: {reason}" for path, reason in sorted(rejections.items()))
        super().__init__(detail or "invalid delta")


def join(parts: Iterable[Any]) -> str:
    return "/".join(str(part) for part in parts)


def _is_container(value) -> bool:
    return isinstance(value, (dict, list))


def flatten(tree, prefix: tuple = ()) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    items = tree.items() if isinstance(tree, dict) else enumerate(tree)
    for key, value in items:
        path = prefix + (key,)
        if _is_container(value):
            flat.update(flatten(value, path))
        else:
            flat[join(path)] = value
    return flat


def _child(container, key):
    if isinstance(container, dict):
        return container[key]
    index = int(key)
    if index < 0:
        raise IndexError(index)
    return container[index]


def _assign(container, key, value):
    if isinstance(container, dict):
        container[key] = value
    else:
        container[int(key)] = value


def coerce(current, incoming, path: str) -> Any:
    if isinstance(current, bool):
        if isinstance(incoming, bool):
            return incoming
        raise ValueError(f"expected a boolean, got {type(incoming).__name__}")

    if isinstance(incoming, bool):
        raise ValueError(f"expected {type(current).__name__}, got a boolean")

    if isinstance(current, int):
        if isinstance(incoming, int):
            return incoming
        if isinstance(incoming, float):
            if not math.isfinite(incoming):
                raise ValueError("not a finite number")
            if not float(incoming).is_integer():
                raise ValueError(f"expected a whole number, got {incoming!r}")
            return int(incoming)
        raise ValueError(f"expected an integer, got {type(incoming).__name__}")

    if isinstance(current, float):
        if isinstance(incoming, (int, float)):
            if not math.isfinite(incoming):
                raise ValueError("not a finite number")
            return float(incoming)
        raise ValueError(f"expected a number, got {type(incoming).__name__}")

    if isinstance(current, str):
        if isinstance(incoming, str):
            return incoming
        raise ValueError(f"expected a string, got {type(incoming).__name__}")

    if current is None:
        raise ValueError("no type to check against (existing value is null)")

    raise ValueError(f"unsupported leaf type {type(current).__name__} at {path}")


def _plan(target, delta, prefix: tuple, writes: list, rejections: dict) -> None:
    if not isinstance(delta, dict):
        rejections[join(prefix)] = "expected an object here"
        return

    for key, incoming in delta.items():
        path = join(prefix + (key,))
        try:
            current = _child(target, key)
        except (KeyError, IndexError, ValueError, TypeError):
            rejections[path] = "no such setting"
            continue

        if isinstance(current, dict):
            _plan(current, incoming, prefix + (key,), writes, rejections)
            continue

        if isinstance(current, list):
            if not isinstance(incoming, list):
                if isinstance(incoming, dict):
                    _plan(current, incoming, prefix + (key,), writes, rejections)
                else:
                    rejections[path] = f"expected a list of {len(current)} items"
                continue
            if len(incoming) != len(current):
                rejections[path] = (f"expected {len(current)} items, "
                                    f"got {len(incoming)}")
                continue
            _plan(current, {str(i): v for i, v in enumerate(incoming)},
                  prefix + (key,), writes, rejections)
            continue

        try:
            value = coerce(current, incoming, path)
        except ValueError as exc:
            rejections[path] = str(exc)
            continue
        if value != current or type(value) is not type(current):
            writes.append((target, key, path, current, value))


def reserved_ports() -> dict:
    try:
        from api import server
    except Exception:
        return {}
    return {server.HTTP_PORT: "the control API",
            server.WS_PORT: "the control API"}


def _check_ports(target, writes, rejections) -> None:
    proposed = {path: value for _container, _key, path, _old, value in writes
                if path in PORT_PATHS}
    if not proposed:
        return
    reserved = reserved_ports()
    settled = {}
    for path in PORT_PATHS:
        section, leaf = path.split("/")
        settled[path] = proposed.get(path, target.get(section, {}).get(leaf))
    for path, value in proposed.items():
        if not isinstance(value, int) or not PORT_LOW <= value <= PORT_HIGH:
            rejections[path] = f"a port must be between {PORT_LOW} and {PORT_HIGH}"
        elif value in reserved:
            rejections[path] = f"{value} belongs to {reserved[value]}"
        else:
            taken = [other.split("/")[1] for other in PORT_PATHS
                     if other != path and settled[other] == value]
            if taken:
                rejections[path] = f"{value} is already {taken[0]}"


class Change:

    __slots__ = ("tree", "changed", "derived", "restart_required")

    def __init__(self, tree: str, changed: dict, derived: dict, restart: list):
        self.tree = tree
        self.changed = changed
        self.derived = derived
        self.restart_required = restart

    def as_dict(self) -> dict:
        return {
            "tree": self.tree,
            "changed": self.changed,
            "derived": self.derived,
            "restart_required": self.restart_required,
        }

    def __bool__(self) -> bool:
        return bool(self.changed or self.derived)

    def __repr__(self) -> str:
        return f"<Change {self.tree} {sorted(self.changed)}>"


TREES: dict[str, tuple[str, bool]] = {
    "config": ("config", True),
    "default_data": ("default_data", True),
    "data": ("data", False),
    "hotkey_config": ("hotkey_config", False),
    "smoothing_config": ("smoothing_config", False),
    "gesture_config": ("gesture_config", False),
}


class ConfigStore:

    def __init__(self, globals_module=None):
        if globals_module is None:
            import utils.globals as globals_module
        self._g = globals_module
        self._lock = threading.RLock()
        self._subscribers: list[Callable[[Change], None]] = []

    def tree(self, name: str):
        try:
            attribute, _writable = TREES[name]
        except KeyError:
            raise KeyError(f"unknown tree {name!r}") from None
        return getattr(self._g, attribute)

    def writable(self, name: str) -> bool:
        return name in TREES and TREES[name][1]

    def snapshot(self, name: str):
        from copy import deepcopy
        with self._lock:
            return deepcopy(self.tree(name))

    def flat(self, name: str) -> dict[str, Any]:
        with self._lock:
            return flatten(self.tree(name))

    def apply(self, name: str, delta: dict) -> Change:
        if not self.writable(name):
            raise DeltaError({name: "this tree is read-only"})
        if not isinstance(delta, dict):
            raise DeltaError({name: "expected an object"})

        with self._lock:
            target = self.tree(name)
            writes: list = []
            rejections: dict[str, str] = {}
            _plan(target, delta, (), writes, rejections)
            if name == "config":
                _check_ports(target, writes, rejections)
            if rejections:
                raise DeltaError(rejections)

            changed: dict[str, dict] = {}
            for container, key, path, old, new in writes:
                _assign(container, key, new)
                changed[path] = {"from": old, "to": new}

            derived = self._derive(name, changed)

        self._persist(name, changed)

        change = Change(
            name, changed, derived,
            sorted({f"{name}/{p}" for p in list(changed) + list(derived)}
                   & RESTART_REQUIRED),
        )
        if change:
            self._notify(change)
        return change

    def _persist(self, name: str, changed: dict) -> None:
        if name != "config":
            return
        from utils.config import save_setting
        for path in STICKY:
            if path in changed:
                save_setting(path.split("/", 1)[1], changed[path]["to"])

    def _derive(self, name: str, changed: dict) -> dict[str, dict]:
        if name != "config":
            return {}
        triggers = ("Setting/camera_performance", "Setting/camera_aspect")
        if not any(path in changed for path in triggers):
            return {}

        setting = self.tree("config")["Setting"]
        preset = normalise_preset(setting.get("camera_performance"))
        aspect = normalise_aspect(setting.get("camera_aspect"))
        width, height, fps = resolution_for(preset, aspect)

        derived: dict[str, dict] = {}
        for key, value in (("camera_performance", preset), ("camera_aspect", aspect),
                           ("camera_width", width), ("camera_height", height),
                           ("camera_fps", fps)):
            old = setting.get(key)
            if old != value:
                setting[key] = value
                path = f"Setting/{key}"
                if path in changed:
                    changed[path]["to"] = value
                else:
                    derived[path] = {"from": old, "to": value}
        return derived

    def subscribe(self, callback: Callable[[Change], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)
        return lambda: self.unsubscribe(callback)

    def unsubscribe(self, callback) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def _notify(self, change: Change) -> None:
        with self._lock:
            listeners = list(self._subscribers)
        for callback in listeners:
            try:
                callback(change)
            except Exception as exc:
                print(f"[api] subscriber {callback!r} raised: {exc}")


_store: ConfigStore | None = None


def store() -> ConfigStore:
    global _store
    if _store is None:
        _store = ConfigStore()
    return _store
