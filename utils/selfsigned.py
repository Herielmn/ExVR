from __future__ import annotations

import hashlib
import secrets
import time


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + _len(len(body)) + body


def _int(value: int) -> bytes:
    body = value.to_bytes((value.bit_length() + 8) // 8 or 1, "big")
    return _tlv(0x02, body)


def _bitstring(body: bytes) -> bytes:
    return _tlv(0x03, b"\x00" + body)


def _octets(body: bytes) -> bytes:
    return _tlv(0x04, body)


def _null() -> bytes:
    return b"\x05\x00"


def _oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    body = bytes([parts[0] * 40 + parts[1]])
    for part in parts[2:]:
        chunk = bytes([part & 0x7F])
        part >>= 7
        while part:
            chunk = bytes([0x80 | (part & 0x7F)]) + chunk
            part >>= 7
        body += chunk
    return _tlv(0x06, body)


def _seq(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _set(*items: bytes) -> bytes:
    return _tlv(0x31, b"".join(items))


def _utf8(text: str) -> bytes:
    return _tlv(0x0C, text.encode("utf-8"))


def _utctime(epoch: float) -> bytes:
    return _tlv(0x17, time.strftime("%y%m%d%H%M%SZ", time.gmtime(epoch)).encode("ascii"))


def _explicit(index: int, body: bytes) -> bytes:
    return _tlv(0xA0 | index, body)


OID_RSA_ENCRYPTION = "1.2.840.113549.1.1.1"
OID_SHA256_WITH_RSA = "1.2.840.113549.1.1.11"
OID_SHA256 = "2.16.840.1.101.3.4.2.1"
OID_COMMON_NAME = "2.5.4.3"
OID_ORGANISATION = "2.5.4.10"
OID_KEY_USAGE = "2.5.29.15"
OID_SUBJECT_ALT_NAME = "2.5.29.17"
OID_BASIC_CONSTRAINTS = "2.5.29.19"
OID_EXT_KEY_USAGE = "2.5.29.37"
OID_SERVER_AUTH = "1.3.6.1.5.5.7.3.1"

_ALGO_SHA256_RSA = _seq(_oid(OID_SHA256_WITH_RSA), _null())


_SMALL_PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59,
                 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113]


def _is_probable_prime(n: int, rounds: int = 40) -> bool:
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _random_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (3 << (bits - 2)) | 1
        if _is_probable_prime(candidate):
            return candidate


class RsaKey:

    __slots__ = ("n", "e", "d", "p", "q", "dp", "dq", "qinv", "size")

    def __init__(self, bits: int = 2048) -> None:
        self.e = 65537
        half = bits // 2
        while True:
            self.p = _random_prime(half)
            self.q = _random_prime(half)
            if self.p == self.q:
                continue
            phi = (self.p - 1) * (self.q - 1)
            if phi % self.e:
                break
        self.n = self.p * self.q
        self.d = pow(self.e, -1, phi)
        self.dp = self.d % (self.p - 1)
        self.dq = self.d % (self.q - 1)
        self.qinv = pow(self.q, -1, self.p)
        self.size = (self.n.bit_length() + 7) // 8

    def public_key_info(self) -> bytes:
        rsa_public_key = _seq(_int(self.n), _int(self.e))
        return _seq(_seq(_oid(OID_RSA_ENCRYPTION), _null()), _bitstring(rsa_public_key))

    def private_der(self) -> bytes:
        return _seq(_int(0), _int(self.n), _int(self.e), _int(self.d), _int(self.p),
                    _int(self.q), _int(self.dp), _int(self.dq), _int(self.qinv))

    def sign_sha256(self, message: bytes) -> bytes:
        digest_info = _seq(_seq(_oid(OID_SHA256), _null()),
                           _octets(hashlib.sha256(message).digest()))
        padding = b"\xff" * (self.size - len(digest_info) - 3)
        encoded = b"\x00\x01" + padding + b"\x00" + digest_info
        signature = pow(int.from_bytes(encoded, "big"), self.d, self.n)
        return signature.to_bytes(self.size, "big")


def _extension(oid: str, value: bytes, critical: bool = False) -> bytes:
    items = [_oid(oid)]
    if critical:
        items.append(b"\x01\x01\xff")
    items.append(_octets(value))
    return _seq(*items)


def _general_names(names: list[str]) -> bytes:
    encoded = []
    for name in names:
        octets = name.split(".")
        if len(octets) == 4 and all(o.isdigit() and 0 <= int(o) < 256 for o in octets):
            encoded.append(_tlv(0x87, bytes(int(o) for o in octets)))
        else:
            encoded.append(_tlv(0x82, name.encode("ascii")))
    return _seq(*encoded)


def generate(names: list[str], common_name: str = "ExVR", bits: int = 2048,
             days: int = 3650) -> tuple[bytes, bytes]:
    key = RsaKey(bits)
    now = time.time()
    subject = _seq(
        _set(_seq(_oid(OID_ORGANISATION), _utf8("ExVR-Next"))),
        _set(_seq(_oid(OID_COMMON_NAME), _utf8(common_name))),
    )
    tbs = _seq(
        _explicit(0, _int(2)),
        _int(secrets.randbits(64) | 1),
        _ALGO_SHA256_RSA,
        subject,
        _seq(_utctime(now - 3600), _utctime(now + days * 86400)),
        subject,
        key.public_key_info(),
        _explicit(3, _seq(
            _extension(OID_BASIC_CONSTRAINTS, _seq(b"\x01\x01\xff"), critical=True),
            _extension(OID_KEY_USAGE, b"\x03\x02\x02\xa4", critical=True),
            _extension(OID_EXT_KEY_USAGE, _seq(_oid(OID_SERVER_AUTH))),
            _extension(OID_SUBJECT_ALT_NAME, _general_names(names)),
        )),
    )
    certificate = _seq(tbs, _ALGO_SHA256_RSA, _bitstring(key.sign_sha256(tbs)))
    return _pem("CERTIFICATE", certificate), _pem("RSA PRIVATE KEY", key.private_der())


def _pem(label: str, der: bytes) -> bytes:
    import base64
    body = base64.b64encode(der)
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    header = f"-----BEGIN {label}-----".encode("ascii")
    footer = f"-----END {label}-----".encode("ascii")
    return b"\n".join([header, *lines, footer]) + b"\n"
