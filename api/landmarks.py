from __future__ import annotations

import utils.globals as g
from tracker.face.face import FACE_CONNECTIONS
from tracker.hand.directml_hands import HAND_CONNECTIONS

TONGUE_INDICES = (57, 287, 164, 18)

FACE_INDICES = tuple(sorted(
    {index for edge in FACE_CONNECTIONS for index in edge} | set(TONGUE_INDICES)
))
_FACE_SLOT = {index: slot for slot, index in enumerate(FACE_INDICES)}

TONGUE_OUT_SLOT = 52
TONGUE_X_SLOT = 62
TONGUE_Y_SLOT = 63

PRECISION = 4


def topology() -> dict:
    return {
        "face_indices": list(FACE_INDICES),
        "face_edges": [[_FACE_SLOT[a], _FACE_SLOT[b]] for a, b in FACE_CONNECTIONS
                       if a in _FACE_SLOT and b in _FACE_SLOT],
        "hand_edges": [list(edge) for edge in HAND_CONNECTIONS],
        "tongue_slots": [_FACE_SLOT[i] for i in TONGUE_INDICES],
    }


def _round(value) -> float:
    return round(float(value), PRECISION)


def _blendshape(slot: int) -> float:
    try:
        return float(g.data["BlendShapes"][slot]["v"])
    except (KeyError, IndexError, TypeError, ValueError):
        return 0.0


def snapshot() -> dict:
    faces = []
    face_landmarks = g.face_landmarks
    if face_landmarks:
        for landmarks in face_landmarks:
            if len(landmarks) <= FACE_INDICES[-1]:
                continue
            faces.append([[_round(landmarks[i].x), _round(landmarks[i].y)]
                          for i in FACE_INDICES])

    hands = []
    hand_landmarks = g.hand_landmarks
    handedness = g.handedness
    if hand_landmarks and handedness:
        for hand, landmarks in zip(handedness, hand_landmarks):
            points = getattr(landmarks, "landmark", None)
            if points is None:
                continue
            hands.append({
                "hand": _handedness_name(hand),
                "points": [[_round(p.x), _round(p.y)] for p in points],
            })

    return {
        "faces": faces,
        "hands": hands,
        "tongue": {
            "out": _round(_blendshape(TONGUE_OUT_SLOT)),
            "x": _round(_blendshape(TONGUE_X_SLOT)),
            "y": _round(_blendshape(TONGUE_Y_SLOT)),
        },
        "fps": _round(g.current_fps),
    }


def _handedness_name(hand) -> str:
    for attribute in ("classification", "label"):
        value = getattr(hand, attribute, None)
        if isinstance(value, str):
            return value
        if value:
            label = getattr(value[0], "label", None) if isinstance(value, (list, tuple)) else None
            if label:
                return label
    return str(hand)
