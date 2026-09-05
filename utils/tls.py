from __future__ import annotations

import os
import ssl
import time

from utils.paths import app_path
from utils import selfsigned

SSL_DIR = ("settings", "ssl")
CERT_NAME = "cert.pem"
KEY_NAME = "key.pem"

RENEW_WITHIN_DAYS = 30

BASE_NAMES = ("localhost", "127.0.0.1")


def credential_paths() -> tuple[str, str]:
    directory = app_path(*SSL_DIR)
    return str(directory / CERT_NAME), str(directory / KEY_NAME)


def _describe(cert_path: str) -> dict | None:
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=cert_path)
        certs = context.get_ca_certs()
    except (OSError, ssl.SSLError):
        return None
    return certs[0] if certs else None


def _covered_names(info: dict) -> set[str]:
    return {value for _, value in info.get("subjectAltName", ())}


def _expires_at(info: dict) -> float:
    try:
        return ssl.cert_time_to_seconds(info["notAfter"])
    except (KeyError, ValueError):
        return 0.0


def _reason_to_regenerate(cert_path: str, key_path: str,
                          names: list[str]) -> str | None:
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        return "no certificate yet"

    info = _describe(cert_path)
    if info is None:
        return "existing certificate is unreadable"

    remaining = _expires_at(info) - time.time()
    if remaining < RENEW_WITHIN_DAYS * 86400:
        days = remaining / 86400
        return f"certificate expires in {days:.0f} day(s)"

    missing = set(names) - _covered_names(info)
    if missing:
        return "certificate does not cover %s" % ", ".join(sorted(missing))

    try:
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(certfile=cert_path, keyfile=key_path)
    except (OSError, ssl.SSLError) as exc:
        return f"certificate and key do not load together ({exc.__class__.__name__})"

    return None


def _write_private(path: str, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def ensure_server_credentials(extra_names=()) -> tuple[str, str]:
    names = list(BASE_NAMES) + [n for n in extra_names if n not in BASE_NAMES]
    cert_path, key_path = credential_paths()

    reason = _reason_to_regenerate(cert_path, key_path, names)
    if reason is None:
        return cert_path, key_path

    print(f"[tls] generating a certificate for this install ({reason})")
    started = time.perf_counter()
    cert_pem, key_pem = selfsigned.generate(names)
    os.makedirs(os.path.dirname(cert_path), exist_ok=True)
    with open(cert_path, "wb") as fh:
        fh.write(cert_pem)
    _write_private(key_path, key_pem)
    print(f"[tls] done in {time.perf_counter() - started:.1f} s, valid for "
          f"{', '.join(names)}")
    return cert_path, key_path
