from __future__ import annotations

CAMERA_PERFORMANCE_PRESETS = [
    ("Max Performance", {"4:3": (192, 144), "16:9": (256, 144)}),
    ("Performance", {"4:3": (320, 240), "16:9": (320, 180)}),
    ("Balanced", {"4:3": (640, 480), "16:9": (640, 360)}),
    ("Quality", {"4:3": (800, 600), "16:9": (800, 450)}),
]

CAMERA_TARGET_FPS = 60

ASPECTS = ("16:9", "4:3")
DEFAULT_ASPECT = "4:3"
DEFAULT_PRESET = 3


def normalise_aspect(aspect) -> str:
    return aspect if aspect in ASPECTS else DEFAULT_ASPECT


def normalise_preset(index) -> int:
    try:
        index = int(index)
    except (TypeError, ValueError):
        return DEFAULT_PRESET
    if 1 <= index <= len(CAMERA_PERFORMANCE_PRESETS):
        return index
    return DEFAULT_PRESET


def resolution_for(preset_index, aspect) -> tuple[int, int, int]:
    _label, resolutions = CAMERA_PERFORMANCE_PRESETS[normalise_preset(preset_index) - 1]
    width, height = resolutions[normalise_aspect(aspect)]
    return width, height, CAMERA_TARGET_FPS


def preset_for_resolution(width, height) -> int | None:
    try:
        wanted = (int(width), int(height))
    except (TypeError, ValueError):
        return None
    for index, (_label, resolutions) in enumerate(CAMERA_PERFORMANCE_PRESETS, start=1):
        if wanted in resolutions.values():
            return index
    return None
