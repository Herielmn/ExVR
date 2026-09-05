from __future__ import annotations

import io
import json
import os
import platform
import sys
import time
import zipfile
from copy import deepcopy
from urllib.parse import urlsplit

from utils import logfile, metrics
from utils.paths import app_path
from utils.version import VERSION

REDACTED = {
    "Setting/camera_ip": "url",
}

BUNDLE_PREFIX = "exvr-diagnostics"


def _redact_url(value: str) -> str:
    if not value:
        return value
    parts = urlsplit(value)
    if not parts.scheme:
        return "<redacted>"
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    credential = "<user:pass>@" if (parts.username or parts.password) else ""
    return f"{parts.scheme}://{credential}{host}{port}<path redacted>"


def scrub(config: dict) -> tuple[dict, list[str]]:
    clean = deepcopy(config)
    touched = []
    for path, kind in REDACTED.items():
        section, _, key = path.rpartition("/")
        node = clean
        for part in section.split("/") if section else []:
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if not isinstance(node, dict) or key not in node:
            continue
        original = node[key]
        if not original:
            continue
        node[key] = _redact_url(original) if kind == "url" else "<redacted>"
        touched.append(path)
    return clean, touched


def _versions() -> dict:
    found = {}
    for name in ("onnxruntime", "numpy", "cv2", "websockets", "flask", "psutil"):
        try:
            module = __import__(name, fromlist=["__version__"])
        except Exception as exc:
            found[name] = f"<import failed: {exc.__class__.__name__}>"
            continue
        found[name] = getattr(module, "__version__", None) or "<no __version__>"
    return found


def _providers() -> dict:
    try:
        import onnxruntime as ort
    except Exception as exc:
        return {"error": repr(exc)}
    info = {"available": list(ort.get_available_providers())}
    try:
        from utils.model_provider import providers_for
        info["selected_gpu"] = providers_for("GPU")
        info["selected_cpu"] = providers_for("CPU")
    except Exception as exc:
        info["selection_error"] = repr(exc)
    return info


def _model_files() -> list[dict]:
    entries = []
    for folder in ("modules", "models"):
        root = app_path(folder)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                stat = path.stat()
                entries.append({
                    "path": str(path.relative_to(app_path())),
                    "bytes": stat.st_size,
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S",
                                              time.localtime(stat.st_mtime)),
                })
    return entries


def _cameras() -> list[str]:
    try:
        from cv2_enumerate_cameras import enumerate_cameras
        import cv2
        return [f"{info.index}: {info.name} [{info.backend}]"
                for info in enumerate_cameras(cv2.CAP_MSMF)]
    except Exception as exc:
        return [f"<enumeration failed: {exc!r}>"]


def manifest(config: dict, extra: dict | None = None) -> dict:
    clean, redacted = scrub(config)
    body = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "app_version": VERSION,
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "elevated": _is_elevated(),
        "metrics_enabled": metrics.ENABLED,
        "redacted_paths": redacted,
        "versions": _versions(),
        "onnxruntime_providers": _providers(),
    }
    if extra:
        body.update(extra)
    return body


def _is_elevated() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def build(config: dict, extra: dict | None = None, preview_jpeg: bytes | None = None) -> tuple[str, bytes]:
    clean, _redacted = scrub(config)
    name = f"{BUNDLE_PREFIX}-{time.strftime('%Y%m%d-%H%M%S')}.zip"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def write_json(entry, payload):
            try:
                archive.writestr(entry, json.dumps(payload, indent=2, default=str))
            except Exception as exc:
                archive.writestr(entry + ".error", repr(exc))

        write_json("manifest.json", manifest(config, extra))
        write_json("config.json", clean)
        write_json("metrics.json", metrics.snapshot())
        archive.writestr("metrics.txt", metrics.format_table())
        write_json("models.json", _model_files())
        archive.writestr("cameras.txt", "\n".join(_cameras()))
        archive.writestr("log.txt", logfile.tail())
        if preview_jpeg:
            archive.writestr("preview.jpg", preview_jpeg)
    return name, buffer.getvalue()
