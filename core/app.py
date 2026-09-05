from __future__ import annotations

import os
import queue
import threading
import time
import traceback
from ctypes import windll

import cv2
from cv2_enumerate_cameras import enumerate_cameras

import utils.globals as g
from api import commands as api_commands
from api import server as api_server
from api import state as api_state
from core.capture import CaptureThread, preview_broker
from tracker.controller.controller import ControllerApp
from utils import drivers
from utils.actions import reset_eye, reset_hand, reset_head
from utils.camera_presets import (
    ASPECTS,
    CAMERA_PERFORMANCE_PRESETS,
    DEFAULT_ASPECT,
    DEFAULT_PRESET,
    normalise_aspect,
    preset_for_resolution,
    resolution_for,
)
from utils.hotkeys import apply_hotkeys, stop_hotkeys
from utils.language import LANGUAGE_OPTIONS, bilingual

PROCESS_PRIORITY_OPTIONS = [
    ("IDLE_PRIORITY_CLASS", "Idle"),
    ("BELOW_NORMAL_PRIORITY_CLASS", "Below Normal"),
    ("NORMAL_PRIORITY_CLASS", "Normal"),
    ("ABOVE_NORMAL_PRIORITY_CLASS", "Above Normal"),
    ("HIGH_PRIORITY_CLASS", "High"),
    ("REALTIME_PRIORITY_CLASS", "Realtime"),
]

PRIORITY_CLASSES = {
    "IDLE_PRIORITY_CLASS": 0x00000040,
    "BELOW_NORMAL_PRIORITY_CLASS": 0x00004000,
    "NORMAL_PRIORITY_CLASS": 0x00000020,
    "ABOVE_NORMAL_PRIORITY_CLASS": 0x00008000,
    "HIGH_PRIORITY_CLASS": 0x00000080,
    "REALTIME_PRIORITY_CLASS": 0x00000100,
}

PRESET_LABELS = {
    "Max Performance": ["Max Performance", "极致性能"],
    "Performance": ["Performance", "性能"],
    "Balanced": ["Balanced", "均衡"],
    "Quality": ["Quality", "画质"],
}
PRIORITY_LABELS = {
    "Idle": ["Idle", "空闲"],
    "Below Normal": ["Below Normal", "低于正常"],
    "Normal": ["Normal", "正常"],
    "Above Normal": ["Above Normal", "高于正常"],
    "High": ["High", "高"],
    "Realtime": ["Realtime", "实时"],
}
LANGUAGE_LABELS = {
    "Auto": ["Auto", "跟随系统"],
    "English": ["English", "English"],
    "简体中文": ["简体中文", "简体中文"],
}

STOP_TIMEOUT = 3.0

QUIT_POLL = 0.5


class Core:

    def __init__(self):
        self.video_thread = None
        self.controller_thread = None
        self.camera_devices = []
        self.camera_index = 0
        self.install_state = False
        self.steamvr_installed = False
        self._install_probe = (0.0, None)
        self._commands = queue.Queue()
        self._worker = None
        self._preview_hold = False
        self._lock = threading.RLock()
        self._quit = threading.Event()

    def start(self):
        self.refresh_cameras()
        self.normalise_camera_settings()
        self.check_installed_components()
        self.register_api_commands()
        api_state.store().subscribe(self._config_changed)
        self._worker = threading.Thread(target=self._serve_commands,
                                        name="Command", daemon=True)
        self._worker.start()

    def wait(self):
        while not self._quit.wait(QUIT_POLL):
            pass

    def shutdown(self):
        self._commands.put(None)
        self.thread_stopped()

    @property
    def tracking_active(self):
        thread = self.video_thread
        return thread is not None and thread.is_alive()

    @property
    def preview_active(self):
        return preview_broker.wanted

    def register_api_commands(self):

        def queue(name, **arguments):
            self._commands.put((name, arguments))
            return {"queued": name}

        for name, description in (
            ("start_tracking", "Start the capture and tracking threads"),
            ("stop_tracking", "Stop tracking and release the camera"),
            ("toggle_tracking", "Start if stopped, stop if running"),
            ("show_preview", "Turn the frame preview on"),
            ("hide_preview", "Turn the frame preview off"),
            ("toggle_preview", "Flip the frame preview"),
            ("reset_head", "Recentre the head"),
            ("reset_eyes", "Recentre the eyes"),
            ("reset_left_hand", "Recentre the left hand"),
            ("reset_right_hand", "Recentre the right hand"),
            ("stop_hotkeys", "Release every held hotkey"),
            ("reset_hotkeys", "Reload the hotkey bindings"),
            ("install_components", "Install the SteamVR drivers, or remove them "
                                   "if they are already installed"),
            ("quit", "Close the core: stop tracking, release the ports, exit"),
        ):
            api_commands.register(name, (lambda n=name: queue(n)), description)

        api_commands.register(
            "select_camera",
            lambda index=0, name=None: queue("select_camera", index=index, name=name),
            "Pick the capture device, by list index or by name")

        api_commands.register_query("tracking_active", lambda: self.tracking_active)
        api_commands.register_query("preview_active", lambda: self.preview_active)
        api_commands.register_query("steamvr_present",
                                    lambda: self._install_state()[3] is not None)
        api_commands.register_query("driver_installed",
                                    lambda: bool(self._install_state()[0]))
        api_commands.register_query("choices", self.api_choices)

    def _serve_commands(self):
        while True:
            item = self._commands.get()
            if item is None:
                return
            name, arguments = item
            self._run_api_command(name, arguments)

    def _run_api_command(self, name, arguments=None):
        arguments = arguments or {}
        tracking = self.tracking_active
        preview_on = self.preview_active
        try:
            if name == "start_tracking":
                if not tracking:
                    self.toggle_camera()
            elif name == "stop_tracking":
                if tracking:
                    self.toggle_camera()
            elif name == "toggle_tracking":
                self.toggle_camera()
            elif name == "show_preview":
                if tracking and not preview_on:
                    self.set_preview(True)
            elif name == "hide_preview":
                if tracking and preview_on:
                    self.set_preview(False)
            elif name == "toggle_preview":
                self.set_preview(not preview_on)
            elif name == "reset_head":
                reset_head()
            elif name == "reset_eyes":
                reset_eye()
            elif name == "reset_left_hand":
                reset_hand(True)
            elif name == "reset_right_hand":
                reset_hand(False)
            elif name == "stop_hotkeys":
                stop_hotkeys()
            elif name == "reset_hotkeys":
                self.reset_hotkeys()
            elif name == "select_camera":
                self.select_camera(arguments.get("index", 0), arguments.get("name"))
            elif name == "install_components":
                self.install_function()
            elif name == "quit":
                self._quit.set()
                return
            else:
                print(f"[api] no core handler for command {name!r}")
                return
        except Exception:
            traceback.print_exc()
        api_server.notify_status()

    def camera_names(self):
        dshow, msmf = [], []
        for device in enumerate_cameras(cv2.CAP_ANY):
            if device.index > 1000:
                msmf.append(f"{device.name} (MSMF)")
            else:
                dshow.append(f"{device.name} (DSHOW)")
        return dshow + msmf

    def refresh_cameras(self):
        self.camera_devices = self.camera_names()
        if self.camera_index >= len(self.camera_devices):
            self.camera_index = 0

    def get_camera_source(self, selected_camera_name):
        devices = enumerate_cameras(cv2.CAP_ANY)
        for device in devices:
            if device.index > 1000:
                device.name += " (MSMF)"
            else:
                device.name += " (DSHOW)"
        for device in devices:
            if device.name == selected_camera_name:
                return device.index
        return 0

    def select_camera(self, index=0, name=None):
        position = -1
        if name and name in self.camera_devices:
            position = self.camera_devices.index(name)
        if position < 0:
            position = int(index)
        if 0 <= position < len(self.camera_devices):
            self.camera_index = position
            print(f"Camera selection: {self.camera_devices[position]}")
        else:
            print(f"[api] no camera at index {position}")

    def resolve_camera_performance_index(self):
        setting = g.config["Setting"]
        configured = setting.get("camera_performance")
        if configured is not None:
            try:
                configured = int(configured)
            except (TypeError, ValueError):
                pass
            else:
                if 1 <= configured <= len(CAMERA_PERFORMANCE_PRESETS):
                    return configured
        recovered = preset_for_resolution(setting["camera_width"],
                                          setting["camera_height"])
        return recovered if recovered is not None else DEFAULT_PRESET

    def resolve_camera_aspect(self):
        return normalise_aspect(g.config["Setting"].get("camera_aspect", DEFAULT_ASPECT))

    def normalise_camera_settings(self):
        setting = g.config["Setting"]
        index = self.resolve_camera_performance_index()
        aspect = self.resolve_camera_aspect()
        width, height, fps = resolution_for(index, aspect)
        setting["camera_performance"] = index
        setting["camera_aspect"] = aspect
        setting["camera_width"] = width
        setting["camera_height"] = height
        setting["camera_fps"] = fps

    def api_choices(self):
        self.refresh_cameras()
        return {
            "camera_device": [[index, name]
                              for index, name in enumerate(self.camera_devices)],
            "camera_selected": self.camera_index,
            "camera_performance": [
                [index, PRESET_LABELS.get(label, label)]
                for index, (label, _) in enumerate(CAMERA_PERFORMANCE_PRESETS, start=1)
            ],
            "camera_aspect": [[aspect, aspect] for aspect in ASPECTS],
            "priority": [[key, PRIORITY_LABELS.get(label, label)]
                         for key, label in PROCESS_PRIORITY_OPTIONS],
            "language": [[code, LANGUAGE_LABELS.get(label, label)]
                         for code, label in LANGUAGE_OPTIONS],
            "model_provider": [["GPU", ["GPU", "GPU"]], ["CPU", ["CPU", "CPU"]]],
        }

    def set_preview(self, wanted):
        with self._lock:
            if wanted and not self._preview_hold:
                preview_broker.attach()
                self._preview_hold = True
            elif not wanted and self._preview_hold:
                preview_broker.detach()
                self._preview_hold = False

    def toggle_camera(self):
        with self._lock:
            if self.tracking_active:
                stop_hotkeys()
                self.thread_stopped()
            else:
                self.normalise_camera_settings()
                apply_hotkeys()
                setting = g.config["Setting"]
                selected = (self.camera_devices[self.camera_index]
                            if self.camera_devices else "")
                source = setting["camera_ip"] or self.get_camera_source(selected)
                self.video_thread = CaptureThread(source,
                                                  setting["camera_width"],
                                                  setting["camera_height"],
                                                  setting["camera_fps"])
                self.video_thread.start()
                self.controller_thread = ControllerApp(
                    on_connection_changed=self._controller_connection_changed)
                self.controller_thread.start()
            self.set_preview(False)

    def thread_stopped(self):
        with self._lock:
            if self.video_thread:
                self.video_thread.stop()
                self.video_thread.join(STOP_TIMEOUT)
                if self.video_thread.is_alive():
                    print("capture thread did not stop within "
                          f"{STOP_TIMEOUT:.0f}s; abandoning it")
                self.video_thread = None
            if self.controller_thread:
                self.controller_thread.stop()
                self.controller_thread.join(STOP_TIMEOUT)
                if self.controller_thread.is_alive():
                    print("controller thread did not stop within "
                          f"{STOP_TIMEOUT:.0f}s; abandoning it")
                self.controller_thread = None
            self.set_preview(False)

    def reset_hotkeys(self):
        stop_hotkeys()
        apply_hotkeys()
        if self.video_thread is None:
            stop_hotkeys()

    def _controller_connection_changed(self, hand, connected):
        api_server.notify_change(
            "config", {f"Tracking/{hand}Controller/enable": connected})

    def _config_changed(self, change):
        if change.tree != "config":
            return
        for key in ("LeftController", "RightController"):
            entry = change.changed.get(f"Tracking/{key}/enable")
            if entry is not None:
                self.apply_controller_enable(key, entry["to"])
        priority = change.changed.get("Setting/priority")
        if priority is not None:
            self.set_process_priority(priority["to"])

    def apply_controller_enable(self, key, value):
        if g.controller is None:
            return
        is_left = key == "LeftController"
        target = (g.controller.left_controller if is_left
                  else g.controller.right_controller)
        target.enable = value
        target.force_enable = value
        if not value:
            g.controller.release_controller_inputs(is_left)
            g.controller.disable_hand(target)

    def set_process_priority(self, priority_key=None):
        if priority_key is None:
            priority_key = g.config["Setting"]["priority"]
        if priority_key not in PRIORITY_CLASSES:
            self.display_message(bilingual("Error", "错误"),
                                 bilingual("Invalid priority index", "无效的进程优先级"))
            return False
        handle = windll.kernel32.OpenProcess(0x0200 | 0x0400, False, os.getpid())
        windll.kernel32.SetPriorityClass(handle, PRIORITY_CLASSES[priority_key])
        windll.kernel32.CloseHandle(handle)
        g.config["Setting"]["priority"] = priority_key
        print(f"Process priority set to {priority_key}")
        return True

    def display_message(self, title, message, kind="error"):
        api_server.notice(message, title=title, kind=kind, modal=True)

    def _install_state(self, max_age=10.0):
        stamp, cached = self._install_probe
        if cached is None or time.time() - stamp > max_age:
            cached = self.install_checking()
            self._install_probe = (time.time(), cached)
        return cached

    def install_checking(self):
        return drivers.state()

    def sync_installed_components(self, steamvr_driver_path, vrcfacetracking_path):
        result = drivers.sync(steamvr_driver_path, vrcfacetracking_path)
        if result["error"]:
            result["error"] = (
                bilingual("Could not update installed drivers. Close "
                          "SteamVR/VRCFaceTracking and reopen ExVR.",
                          "无法更新已安装驱动。请关闭 SteamVR/VRCFaceTracking "
                          "后重新打开 ExVR。")
                + f"\n\n{result['error']}"
            )
        return result

    def check_installed_components(self):
        state = self.install_checking()
        result = self.sync_installed_components(state[1], state[2])
        if result["error"] is None:
            state = self.install_checking()
        self.install_state, _driver_path, _vrcft_path, steamvr_path = state
        self.steamvr_installed = steamvr_path is not None
        self._install_probe = (time.time(), state)
        title = bilingual("Driver Update", "驱动更新")
        if result["error"]:
            self.display_message(title, result["error"])
        elif result["updated"]:
            self.display_message(
                title,
                bilingual("Updated installed components:", "已更新安装组件：")
                + "\n\n" + "\n".join(result["updated"]),
                kind="info")

    def _driver_problem_message(self, problem):
        if problem.reason == "no_steamvr":
            return bilingual("SteamVR is not installed or could not be found.",
                             "SteamVR 未安装或无法找到。")
        if problem.reason == "declined":
            return bilingual(
                "Administrator permission is needed to change SteamVR's drivers "
                "folder, and the request was declined.",
                "修改 SteamVR 的 drivers 目录需要管理员权限，本次请求已被取消。",
            )
        if problem.reason == "vrcft_running":
            text = bilingual("VRCFT is running, please close VRCFT and try again.",
                             "VRCFT 正在运行，请关闭 VRCFT 后重试。")
        elif problem.reason == "steamvr_running":
            text = bilingual(
                "SteamVR's driver files are open in another program, so they cannot "
                "be changed. Close SteamVR and the Steam client, then try again. "
                "Nothing was changed.",
                "SteamVR 的驱动文件正被别的程序占用，无法改动。请关闭 SteamVR 和 "
                "Steam 客户端后重试。本次没有改动任何文件。")
        else:
            text = bilingual("Could not install/update drivers. Close "
                             "SteamVR/VRCFaceTracking and try again.",
                             "无法安装/更新驱动。请关闭 SteamVR/VRCFaceTracking 后重试。")
        return f"{text}\n\n{problem.detail}" if problem.detail else text

    def install_function(self):
        (self.install_state, steamvr_driver_path, vrcfacetracking_path,
         check_steamvr_path) = self.install_checking()
        self.steamvr_installed = check_steamvr_path is not None
        if steamvr_driver_path is None or check_steamvr_path is None:
            self.display_message(
                bilingual("Error", "错误"),
                bilingual("SteamVR is not installed or could not be found.",
                          "SteamVR 未安装或无法找到。"))
            return

        action = "uninstall" if self.install_state else "install"
        problem = drivers.apply(action, steamvr_driver_path, vrcfacetracking_path)
        self._install_probe = (0.0, None)
        if problem is not None:
            self.display_message(bilingual("Error", "错误"),
                                 self._driver_problem_message(problem))
            return

        if action == "uninstall":
            self.install_state = False
            self.display_message(
                bilingual("Driver removed", "驱动已删除"),
                bilingual("VMT and VRto3D are no longer in SteamVR. ExVR's tracking "
                          "will not work until they are installed again.",
                          "已从 SteamVR 移除 VMT 与 VRto3D，ExVR 的追踪功能将不再工作。"),
                kind="info")
        else:
            self.install_state = True
            self.display_message(
                bilingual("Driver installed", "驱动已安装"),
                bilingual("VMT and VRto3D are in place. Restart SteamVR if it is "
                          "running -- it only loads drivers when it starts.",
                          "VMT 与 VRto3D 已写入 SteamVR。若 SteamVR 正在运行请重启它，"
                          "驱动只在启动时加载。"),
                kind="info")
