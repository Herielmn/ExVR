import time

import numpy as np

from utils.json_manager import load_json
from utils import metrics
import utils.globals as g


class VectorKalmanFilter:

    def __init__(self, q_process: float, r_measure: float, dim: int):
        self.dim = dim
        self.q = float(q_process)
        self.r = float(r_measure)
        self.x = None
        self.p = 1.0

    def predict(self, dt: float = 1.0):
        """Time-update (prediction) step."""
        if self.x is None:
            return  # filter not initialised yet
        # Simple random-walk model => F = I, so only P changes
        self.p += self.q * dt * 60 / g.current_fps

    def update(self, z, is_rotation: bool = False):
        """Measurement-update (correction) step.

        Args:
            z            : iterable/np.ndarray of new observations (dim,)
            is_rotation  : treat the measurements as angles in degrees and wrap
                           differences across +/-180 degrees.
        Returns:
            np.ndarray   : the updated state estimate (copy).
        """
        z = np.asarray(z, dtype=np.float64)

        # First measurement initialises the filter
        if self.x is None:
            self.x = z.copy()
            return self.x.copy()

        # Innovation (measurement residual)
        y = angle_delta(z, self.x) if is_rotation else z - self.x

        # Innovation covariance & Kalman gain
        k = self.p * (1.0 / (self.p + self.r))

        # State update
        self.x = self.x + k * y
        self.p = (1.0 - k) * self.p
        return self.x.copy()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def angle_diff(current: float, target: float) -> float:
    """Minimum signed difference from *target* to *current* (deg)."""
    diff = (current - target) % 360.0
    return diff - 360.0 if diff > 180.0 else diff


def angle_delta(current, target):
    diff = np.mod(np.asarray(current, dtype=np.float64)
                  - np.asarray(target, dtype=np.float64), 360.0)
    return np.where(diff > 180.0, diff - 360.0, diff)


def update_target_value(target: dict, smoothed_delta: float, is_rotation: bool):
    """Write the smoothed delta back into the target slot (in-place)."""
    if is_rotation:
        target["v"] = (target["v"] + smoothed_delta) % 360.0
    else:
        target["v"] += smoothed_delta


# ---------------------------------------------------------------------------
# Public API used by the main application
# ---------------------------------------------------------------------------

def setup_smoothing():
    """Load settings/smoothing.json and prepare global structures.

    Returns the parsed configuration so that callers can inspect it if they
    need to.
    """
    smoothing_config = load_json("settings/smoothing.json")

    g.kalman_filters = {}
    g.indices_map = {}
    g.smoothing_config = smoothing_config

    # Build one VectorKalmanFilter per *action* that declares kalman_params.
    for action, params in smoothing_config["Parameters"].items():
        indices = params.get("indices", [])
        g.indices_map[action] = indices  # may be an empty list

        if action == "OtherBlendShapes":
            # Explicitly skip Kalman filter creation for the fallback bucket
            continue

        if "kalman_params" in params and indices:
            q = params["kalman_params"]["q_process"]
            r = params["kalman_params"]["r_measure"]
            dim = len(indices)
            g.kalman_filters[action] = VectorKalmanFilter(q, r, dim)

    _build_plan(smoothing_config)
    return smoothing_config


_PASS1: tuple = ()
_PASS2 = None


def _build_plan(smoothing_config):
    global _PASS1, _PASS2
    steps = []
    handled = set()
    for action, params in smoothing_config["Parameters"].items():
        indices = tuple(g.indices_map.get(action, []))
        if not indices:      # empty index lists fall through to pass 2
            continue
        handled.update(indices)
        shifting = params.get("shifting", 0)
        steps.append((indices,
                      tuple(idx - shifting for idx in indices),
                      params["key"],
                      params.get("is_rotation", False),
                      params.get("dt_multiplier", 20),
                      g.kalman_filters.get(action)))
    _PASS1 = tuple(steps)

    other = smoothing_config["Parameters"].get("OtherBlendShapes", {})
    if not other:
        _PASS2 = None
        return
    shifting = other.get("shifting", 0)
    size = len(g.latest_data) or g.LATEST_DATA_SIZE
    _PASS2 = (tuple((idx, idx - shifting)
                    for idx in range(size) if idx not in handled),
              other.get("key", "blendShapes"),
              other.get("is_rotation", False),
              other.get("dt_multiplier", 20))


def smooth_once(dt_base: float) -> None:
    latest = g.latest_data
    size = len(latest)
    data = g.data
    t_iter = metrics.now()

    # ------------------------------------------------------------------
    # Pass 1 - every *named* action
    # ------------------------------------------------------------------
    for indices, targets, target_key, is_rotation, dt_mul, kf in _PASS1:
        dt = dt_base * dt_mul

        # Gather the observation vector for this action
        try:
            obs_vec = [latest[idx] for idx in indices]
        except IndexError:
            continue          # source array shorter than expected; skip the action

        if kf is not None:
            kf.predict(dt_base)
            filt_vec = kf.update(obs_vec, is_rotation)
        else:
            filt_vec = obs_vec                       # raw values (no KF)

        # Write the smoothed deltas back to the destination buffer
        data_array = data[target_key]
        length = len(data_array)
        for target_idx, raw in zip(targets, filt_vec):
            if not (0 <= target_idx < length):
                continue                             # out of range; ignore
            target = data_array[target_idx]
            delta = angle_diff(raw, target["v"]) if is_rotation else raw - target["v"]
            update_target_value(target, delta * dt, is_rotation)

    # ------------------------------------------------------------------
    # Pass 2 - "OtherBlendShapes" for everything else
    # ------------------------------------------------------------------
    t_pass2 = metrics.now()
    metrics.observe("smooth.pass1", t_pass2 - t_iter)
    if _PASS2 is not None:
        rest, target_key, is_rotation, dt_mul = _PASS2
        dt = dt_base * dt_mul
        data_array = data[target_key]
        length = len(data_array)
        for idx, target_idx in rest:
            if idx >= size or not (0 <= target_idx < length):
                continue
            target = data_array[target_idx]
            raw = latest[idx]
            delta = angle_diff(raw, target["v"]) if is_rotation else raw - target["v"]
            update_target_value(target, delta * dt, is_rotation)

    metrics.observe("smooth.pass2", metrics.now() - t_pass2)
    metrics.observe("smooth.iter", metrics.now() - t_iter)


# ---------------------------------------------------------------------------
# Main worker: runs in its own thread for as long as smoothing is enabled
# ---------------------------------------------------------------------------

def apply_smoothing():
    last_time = time.perf_counter()
    frame_duration = 1.0 / 1000.0

    while not g.stop_event.is_set() and g.config["Smoothing"]["enable"]:
        now = time.perf_counter()
        dt_base = now - last_time            # seconds since the previous iteration
        last_time = now
        metrics.mark("smooth.rate")
        smooth_once(dt_base)
        time.sleep(frame_duration)
