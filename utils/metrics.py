from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any


def base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


FLAG_FILE = "metrics.on"
SNAPSHOT_FILE = "metrics.json"


def _armed() -> bool:
    if os.environ.get("EXVR_METRICS", "").strip().lower() in ("1", "true", "on", "yes"):
        return True
    try:
        return os.path.exists(os.path.join(base_dir(), FLAG_FILE))
    except OSError:
        return False


ENABLED = _armed()
CAPACITY = 240

now = time.perf_counter

_series: dict[str, "_Series"] = {}
_counters: dict[str, int] = {}
_last_mark: dict[str, float] = {}


class _Series:
    __slots__ = ("buf", "i", "n", "cap")

    def __init__(self, cap: int = CAPACITY) -> None:
        self.buf = [0.0] * cap
        self.cap = cap
        self.i = 0
        self.n = 0

    def add(self, v: float) -> None:
        self.buf[self.i] = v
        self.i = (self.i + 1) % self.cap
        self.n += 1

    def samples(self) -> list[float]:
        if self.n < self.cap:
            return self.buf[: self.n]
        return self.buf[self.i:] + self.buf[: self.i]


def enable(on: bool = True) -> None:
    global ENABLED
    ENABLED = on


def reset() -> None:
    _series.clear()
    _counters.clear()
    _last_mark.clear()


def observe(name: str, seconds: float) -> None:
    if not ENABLED:
        return
    s = _series.get(name)
    if s is None:
        s = _series[name] = _Series()
    s.add(seconds)


def mark(name: str) -> None:
    if not ENABLED:
        return
    t = now()
    prev = _last_mark.get(name)
    _last_mark[name] = t
    if prev is not None:
        observe(name, t - prev)


def count(name: str, k: int = 1) -> None:
    if not ENABLED:
        return
    _counters[name] = _counters.get(name, 0) + k


class timer:

    __slots__ = ("name", "t")

    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self) -> "timer":
        self.t = now()
        return self

    def __exit__(self, *exc: Any) -> None:
        observe(self.name, now() - self.t)


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {"timings": {}, "counters": dict(_counters)}
    for name, s in list(_series.items()):
        vals = s.samples()
        if not vals:
            continue
        ordered = sorted(vals)
        total = 0.0
        for v in vals:
            total += v
        out["timings"][name] = {
            "n": s.n,
            "window": len(vals),
            "last_ms": vals[-1] * 1000.0,
            "mean_ms": total / len(vals) * 1000.0,
            "p50_ms": _percentile(ordered, 0.50) * 1000.0,
            "p95_ms": _percentile(ordered, 0.95) * 1000.0,
            "max_ms": ordered[-1] * 1000.0,
            "hz": len(vals) / total if total > 0.0 else 0.0,
        }
    return out


def format_table() -> str:
    snap = snapshot()
    lines = [
        f"{'stage':<26}{'n':>8}{'mean':>9}{'p50':>9}{'p95':>9}{'max':>9}{'hz':>9}",
        "-" * 79,
    ]
    for name in sorted(snap["timings"]):
        d = snap["timings"][name]
        lines.append(
            f"{name:<26}{d['n']:>8}{d['mean_ms']:>9.3f}{d['p50_ms']:>9.3f}"
            f"{d['p95_ms']:>9.3f}{d['max_ms']:>9.3f}{d['hz']:>9.1f}"
        )
    if snap["counters"]:
        lines.append("")
        lines.append(f"{'counter':<26}{'value':>8}")
        lines.append("-" * 34)
        for name in sorted(snap["counters"]):
            lines.append(f"{name:<26}{snap['counters'][name]:>8}")
    return "\n".join(lines)


def dump(path: str) -> None:
    payload = snapshot()
    payload["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


_reporter: threading.Thread | None = None


def start_reporter(interval: float = 5.0) -> None:
    global _reporter
    if not ENABLED or _reporter is not None:
        return

    path = os.path.join(base_dir(), SNAPSHOT_FILE)
    print(f"[metrics] armed; snapshot -> {path}", flush=True)

    def _loop() -> None:
        while True:
            time.sleep(interval)
            if not (_series or _counters):
                continue
            print("\n" + format_table(), flush=True)
            try:
                dump(path)
            except OSError as exc:
                print(f"[metrics] could not write {path}: {exc}", flush=True)

    _reporter = threading.Thread(target=_loop, daemon=True, name="MetricsReporter")
    _reporter.start()
