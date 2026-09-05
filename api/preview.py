from __future__ import annotations

import threading
import time

import cv2

from utils import metrics

MAX_STREAM_FPS = 20.0
JPEG_QUALITY = 70

KEEPALIVE_SECONDS = 0.5

BOUNDARY = "exvrframe"


class FrameBroker:

    def __init__(self):
        self._condition = threading.Condition()
        self._frame = None
        self._sequence = 0
        self._readers = 0
        self._shape: tuple[int, int] | None = None

    @property
    def wanted(self) -> bool:
        return self._readers > 0

    def publish(self, rgb_frame) -> None:
        if self._readers <= 0:
            return
        bgr = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)
        with self._condition:
            self._frame = bgr
            self._shape = (bgr.shape[1], bgr.shape[0])
            self._sequence += 1
            self._condition.notify_all()

    def clear(self) -> None:
        with self._condition:
            self._frame = None
            self._sequence += 1
            self._condition.notify_all()

    def _wait(self, seen: int, timeout: float):
        with self._condition:
            if self._sequence == seen:
                self._condition.wait(timeout)
            return self._sequence, self._frame

    def attach(self) -> None:
        with self._condition:
            self._readers += 1

    def detach(self) -> None:
        with self._condition:
            self._readers = max(0, self._readers - 1)
            if self._readers == 0:
                self._frame = None

    @property
    def size(self):
        return self._shape

    def mjpeg(self, stop=None, max_fps: float = MAX_STREAM_FPS, quality: int = JPEG_QUALITY):
        self.attach()
        interval = 1.0 / max_fps if max_fps > 0 else 0.0
        params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
        seen = -1
        next_allowed = 0.0
        try:
            while stop is None or not stop():
                sequence, frame = self._wait(seen, timeout=KEEPALIVE_SECONDS)
                if sequence == seen:
                    yield b"\r\n"
                    continue
                seen = sequence
                if frame is None:
                    yield b"\r\n"
                    continue
                now = time.perf_counter()
                if now < next_allowed:
                    continue
                next_allowed = now + interval
                started = metrics.now()
                ok, buffer = cv2.imencode(".jpg", frame, params)
                metrics.observe("preview.encode", metrics.now() - started)
                if not ok:
                    continue
                payload = buffer.tobytes()
                metrics.mark("preview.stream")
                yield (b"--" + BOUNDARY.encode() + b"\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n"
                       + payload + b"\r\n")
        finally:
            self.detach()

    def snapshot_jpeg(self, quality: int = JPEG_QUALITY, timeout: float = 2.0):
        self.attach()
        deadline = time.monotonic() + timeout
        try:
            while True:
                with self._condition:
                    if self._frame is not None:
                        frame = self._frame
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._condition.wait(remaining)
            ok, buffer = cv2.imencode(".jpg", frame,
                                      [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
            return buffer.tobytes() if ok else None
        finally:
            self.detach()


_broker: FrameBroker | None = None


def broker() -> FrameBroker:
    global _broker
    if _broker is None:
        _broker = FrameBroker()
    return _broker
