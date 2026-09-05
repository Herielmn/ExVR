import os
import threading

import keyboard
import psutil
import screeninfo
import win32gui, win32process

from utils.actions import *
from utils.json_manager import load_json
from utils.rawinput import RawInputListener

listener = None
monitor = None
_lock = threading.Lock()
_pressed = set()
_chords = {}
_key_press = {}
_key_release = {}
_mouse_actions = {}
_pressed_buttons = set()
_foreground_cache = {}


def toggle_hotkeys():
    g.config["Hotkey"]["enable"] = not g.config["Hotkey"]["enable"]
    print("Hotkey:", g.config["Hotkey"]["enable"])
    if g.config["Hotkey"]["enable"]:
        apply_hotkeys()
    else:
        stop_hotkeys()

actions = {
    "toggle_hotkeys": toggle_hotkeys,
    "reset_eye": reset_eye,
    "disable_eye_yaw": disable_eye_yaw,
    "disable_eye": disable_eye,
    "reset_head": reset_head,
    "up": up,
    "down": down,
    "left": left,
    "right": right,
    "squat": squat,
    "prone": prone,
    "head_pitch_up": lambda: head_pitch(True),
    "head_pitch_down": lambda: head_pitch(False),
    "head_yaw_left": lambda: head_yaw(False),
    "head_yaw_right": lambda: head_yaw(True),
    "grab_left": lambda: grab(True, 2),
    "grab_right": lambda: grab(False, 2),
    "trigger_left": (
        lambda _: trigger_press(True, 0),
        lambda _: trigger_release(True, 0),
    ),
    "trigger_right": (
        lambda _: trigger_press(False, 0),
        lambda _: trigger_release(False, 0),
    ),
    "joystick_up_right": lambda: joystick_up(False, 1),
    "joystick_down_right": lambda: joystick_down(False, 1),
    "joystick_middle_right": lambda: joystick_middle(False, 1),
    "joystick_middle_right_delay": lambda: joystick_middle_delay(False, 1),
    "enable_fingers_left": lambda: enable_fingers(True),
    "enable_fingers_right": lambda: enable_fingers(False),
    "set_finger_0_left": lambda: set_finger(True, 0),
    "set_finger_1_left": lambda: set_finger(True, 1),
    "set_finger_2_left": lambda: set_finger(True, 2),
    "set_finger_3_left": lambda: set_finger(True, 3),
    "set_finger_4_left": lambda: set_finger(True, 4),
    "set_finger_0_right": lambda: set_finger(False, 0),
    "set_finger_1_right": lambda: set_finger(False, 1),
    "set_finger_2_right": lambda: set_finger(False, 2),
    "set_finger_3_right": lambda: set_finger(False, 3),
    "set_finger_4_right": lambda: set_finger(False, 4),
    "toggle_hand_tracking_mode": lambda: toggle_hand_tracking_mode(),
    "enable_hand": enable_hand,
    "reset_hand_left": lambda: reset_hand(True),
    "reset_hand_right": lambda: reset_hand(False),
    "enable_tongue": enable_tongue,
    "set_tongue": set_tongue
}


def setup_hotkeys():
    hotkey_config = load_json("settings/hotkeys.json")
    return hotkey_config

def _in_game_guard(func):
    def wrapper(*args, **kwargs):
        if g.config['Setting']["only_ingame"] and not is_in_game():
            return
        return func(*args, **kwargs)
    return wrapper


def _scan_codes(key):
    try:
        return keyboard.key_to_scan_codes(key)
    except ValueError as exc:
        print(f"[hotkey] {key!r}: {exc}")
        return ()


def _combinations(key):
    try:
        steps = keyboard.parse_hotkey_combinations(key)
    except ValueError as exc:
        print(f"[hotkey] {key!r}: {exc}")
        return ()
    if len(steps) != 1:
        print(f"[hotkey] {key!r} is a key sequence; only chords are supported")
        return ()
    return steps[0]


def _bind_chord(key, callback):
    for combination in _combinations(key):
        _chords.setdefault(combination, []).append(callback)


def _bind_key(key, press, release):
    for scan_code in _scan_codes(key):
        _key_press.setdefault(scan_code, []).append(press)
        _key_release.setdefault(scan_code, []).append(release)


def _clear_bindings():
    with _lock:
        _pressed.clear()
    _chords.clear()
    _key_press.clear()
    _key_release.clear()
    _mouse_actions.clear()
    _pressed_buttons.clear()

def _on_key(scan_code, down):
    with _lock:
        if down:
            _pressed.add(scan_code)
        chord = tuple(sorted(_pressed))
        if not down:
            _pressed.discard(scan_code)
    for callback in (_key_press if down else _key_release).get(scan_code, ()):
        callback(None)
    if down:
        for callback in _chords.get(chord, ()):
            callback()


def _on_button(name, pressed):
    if not _mouse_actions:
        return
    if g.config['Setting']["only_ingame"] and not is_in_game():
        return

    if pressed:
        _pressed_buttons.add(name)
    if "left" in _pressed_buttons and "middle" in _pressed_buttons:
        button = "left+middle"
    elif "right" in _pressed_buttons and "middle" in _pressed_buttons:
        button = "right+middle"
    else:
        button = name
    if not pressed:
        _pressed_buttons.discard(name)

    for action in _mouse_actions.get(button, ()):
        if isinstance(action, tuple):
            if pressed:
                action[0](None)
            else:
                action[1](None)
        elif pressed:
            action()


def _on_wheel(delta):
    if not _mouse_actions:
        return
    if g.config['Setting']["only_ingame"] and not is_in_game():
        return
    for action in _mouse_actions.get("scroll_up" if delta > 0 else "scroll_down", ()):
        if isinstance(action, tuple):
            print("wrong action")
        elif action:
            action()

def _current_monitor(x, y):
    for candidate in screeninfo.get_monitors():
        if candidate.x <= x <= candidate.x + candidate.width \
                and candidate.y <= y <= candidate.y + candidate.height:
            return candidate
    return None


def _on_move(x, y):
    global monitor

    if not _mouse_actions:
        return
    if not g.config['Mouse']["enable"]:
        return
    if g.config['Setting']["only_ingame"] and not is_in_game():
        bound = g.config["Mouse"]["bound_threshold"] - 0.01
        g.latest_data[117] = max(-bound, min(bound, g.latest_data[117]))
        g.latest_data[118] = max(-bound, min(bound, g.latest_data[118]))
        g.data["MousePosition"][0]["v"] = max(-bound, min(bound,
                                            g.data["MousePosition"][0]["v"]))
        g.data["MousePosition"][1]["v"] = max(-bound, min(bound,
                                            g.data["MousePosition"][1]["v"]))
        return
    if monitor is None:
        monitor = _current_monitor(x, y)
        if monitor is None:
            return
    x_normalized = (x / monitor.width - 0.5)
    y_normalized = -(y / monitor.height - 0.5)
    if g.config["Smoothing"]["enable"]:
        g.latest_data[117] = x_normalized
        g.latest_data[118] = y_normalized
    else:
        g.data["MousePosition"][0]["v"] = x_normalized
        g.data["MousePosition"][1]["v"] = y_normalized


def _ensure_listener():
    global listener
    if listener is None:
        listener = RawInputListener(on_key=_on_key, on_button=_on_button,
                                    on_wheel=_on_wheel, on_move=_on_move)
    try:
        listener.start()
    except (OSError, RuntimeError) as exc:
        print(f"[hotkey] raw input unavailable, hotkeys are off: {exc}")

def apply_hotkeys():
    _clear_bindings()

    for item in g.hotkey_config.get("Hotkeys"):
        key = item.get("key")
        mouse_button = item.get("mouse")
        action = item.get("action")
        if action and key:
            if action in actions:
                handler = actions[action]
                if isinstance(handler, tuple):
                    if len(handler) == 2:
                        _bind_key(key, _in_game_guard(handler[0]),
                                  _in_game_guard(handler[1]))
                else:
                    _bind_chord(key, _in_game_guard(handler))
            elif "left_fingers" in action or "right_fingers" in action:
                _bind_chord(key, lambda a=action: set_fingers(a))
        if mouse_button and action:
            if action in actions:
                handler = actions[action]
                slot = _mouse_actions.setdefault(mouse_button, [])
                if isinstance(handler, tuple):
                    slot.append((_in_game_guard(handler[0]),
                                 _in_game_guard(handler[1])))
                else:
                    slot.append(_in_game_guard(handler))

    _ensure_listener()
    print("Start Hotkey")


def stop_hotkeys():
    global monitor
    _clear_bindings()
    monitor = None
    for item in g.hotkey_config["Hotkeys"]:
        if item["action"] == "toggle_hotkeys":
            _bind_chord(item["key"], toggle_hotkeys)
    _ensure_listener()
    print("Stop Hotkey")


def is_in_game():
    hwnd = win32gui.GetForegroundWindow()
    target = g.config['Setting']["only_ingame_game"]
    if win32gui.GetWindowText(hwnd) == target:
        return True

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    cache_key = (hwnd, pid)
    program_name = _foreground_cache.get(cache_key)
    if program_name is None:
        try:
            program_name = os.path.basename(psutil.Process(pid).exe())
        except Exception:
            program_name = ""
        if len(_foreground_cache) > 64:
            _foreground_cache.clear()
        _foreground_cache[cache_key] = program_name
    return program_name == target
