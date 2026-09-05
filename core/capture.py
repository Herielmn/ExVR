from __future__ import annotations

import threading
import traceback

import cv2

import utils.globals as g
import utils.tracking
from api.preview import broker as _preview_broker
from utils import metrics

preview_broker = _preview_broker()


class CaptureThread(threading.Thread):

    def __init__(self, source, width=640, height=480, fps=60):
        super().__init__(name="Capture", daemon=True)
        self.source = source
        self.video_capture = None
        self.is_running = True
        self.show_image = False
        self.tracker = utils.tracking.Tracker()
        self.width = int(width)
        self.height = int(height)
        self.capture_width, self.capture_height = self.capture_request_size(self.width,
                                                                           self.height)
        self.fps = fps

    @staticmethod
    def capture_request_size(width, height):
        if width <= 0 or height <= 0:
            return 640, 480
        aspect_ratio = width / height
        if abs(aspect_ratio - 16 / 9) < abs(aspect_ratio - 4 / 3):
            if width <= 1280 and height <= 720:
                return 1280, 720
            return width, height
        if width <= 640 and height <= 480:
            return 640, 480
        if width <= 800 and height <= 600:
            return 800, 600
        return width, height

    def resize_for_processing(self, rgb_image):
        image_height, image_width = rgb_image.shape[:2]
        if image_width <= 0 or image_height <= 0:
            return rgb_image
        target_ratio = self.width / self.height
        image_ratio = image_width / image_height
        if abs(image_ratio - target_ratio) > 0.01:
            if image_ratio > target_ratio:
                crop_width = int(round(image_height * target_ratio))
                x0 = max(0, (image_width - crop_width) // 2)
                rgb_image = rgb_image[:, x0:x0 + crop_width]
            else:
                crop_height = int(round(image_width / target_ratio))
                y0 = max(0, (image_height - crop_height) // 2)
                rgb_image = rgb_image[y0:y0 + crop_height, :]
        if rgb_image.shape[1] != self.width or rgb_image.shape[0] != self.height:
            rgb_image = cv2.resize(rgb_image, (self.width, self.height),
                                   interpolation=cv2.INTER_AREA)
        return rgb_image

    def run(self):
        try:
            self._capture_loop()
        except Exception:
            metrics.count("capture.crashed")
            traceback.print_exc()
        finally:
            self.cleanup()

    def _capture_loop(self):
        self.video_capture = cv2.VideoCapture(self.source, cv2.CAP_ANY)
        self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.capture_width)
        self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.capture_height)
        self.video_capture.set(cv2.CAP_PROP_FPS, self.fps)
        print(
            "capture",
            self.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH),
            self.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
            self.video_capture.get(cv2.CAP_PROP_FPS),
            "process",
            self.width,
            self.height,
        )
        reported_fps = self.video_capture.get(cv2.CAP_PROP_FPS)
        g.current_fps = reported_fps if reported_fps and reported_fps > 0 \
            else float(self.fps)
        self.video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        while self.is_running:
            t_read = metrics.now()
            ret, frame = self.video_capture.read()
            if ret:
                t_cvt = metrics.now()
                metrics.observe("capture.read", t_cvt - t_read)
                metrics.mark("capture.rate")
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb_image = self.resize_for_processing(rgb_image)
                if g.config["Setting"]["flip_x"]:
                    rgb_image = cv2.flip(rgb_image, 1)
                if g.config["Setting"]["flip_y"]:
                    rgb_image = cv2.flip(rgb_image, 0)
                metrics.observe("capture.convert", metrics.now() - t_cvt)

                t_disp = metrics.now()
                self.tracker.process_frame(rgb_image)
                metrics.observe("dispatch.total", metrics.now() - t_disp)

                preview_broker.publish(rgb_image)
            else:
                metrics.count("capture.read_failed")

    def stop(self):
        self.is_running = False
        self.tracker.stop()

    def cleanup(self):
        preview_broker.clear()
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None
