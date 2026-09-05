from __future__ import annotations

import utils.globals as g
from utils.config import setup_config, save_config
from utils.data import setup_data, save_data
from utils.hand_sender import setup_controller
from utils.hotkeys import setup_hotkeys, apply_hotkeys
from utils.smoothing import setup_smoothing
from tracker.controller.controller import setup_gestures


def load_all() -> None:
    g.config = setup_config()
    g.data, g.default_data = setup_data()
    g.latest_data = [0.0] * g.LATEST_DATA_SIZE
    g.controller = setup_controller()
    g.hotkey_config = setup_hotkeys()
    g.smoothing_config = setup_smoothing()
    g.gesture_config = setup_gestures()


def reload_all() -> None:
    load_all()
    apply_hotkeys()


def save_all() -> None:
    save_config(g.config)
    for index, entry in enumerate(g.data["BlendShapes"]):
        g.default_data["BlendShapes"][index]["s"] = entry["s"]
    save_data(g.default_data)
