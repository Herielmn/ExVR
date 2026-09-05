from __future__ import annotations

import numpy as np

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

_SINGULAR = 1e-7


def _elementary_quat(axis: str, angle: float) -> np.ndarray:
    quat = np.zeros(4)
    quat[_AXIS_INDEX[axis]] = np.sin(angle / 2)
    quat[3] = np.cos(angle / 2)
    return quat


def _compose(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    cross = np.cross(p[:3], q[:3])
    product = np.empty(4)
    product[:3] = p[3] * q[:3] + q[3] * p[:3] + cross
    product[3] = p[3] * q[3] - np.dot(p[:3], q[:3])
    return product


def _parse_seq(seq: str, axes: tuple = (1, 2, 3)) -> tuple[str, bool]:
    if not isinstance(seq, str) or len(seq) not in axes:
        wanted = " or ".join(str(count) for count in axes)
        raise ValueError(f"expected a sequence of {wanted} axes, got {seq!r}")
    if seq.islower():
        intrinsic = False
    elif seq.isupper():
        intrinsic = True
    else:
        raise ValueError(f"mixed extrinsic/intrinsic sequence {seq!r}")
    lowered = seq.lower()
    if any(axis not in _AXIS_INDEX for axis in lowered):
        raise ValueError(f"unknown axis in {seq!r}")
    if any(first == second for first, second in zip(lowered, lowered[1:])):
        raise ValueError(f"consecutive axes must differ, got {seq!r}")
    return lowered, intrinsic


def _quat_from_euler(seq: str, angles, degrees: bool) -> np.ndarray:
    lowered, intrinsic = _parse_seq(seq)
    angles = np.asarray(angles, dtype=float).reshape(-1)
    if angles.shape != (len(lowered),):
        raise ValueError(f"{seq!r} needs {len(lowered)} angle(s), "
                         f"got {angles.size}")
    if degrees:
        angles = np.deg2rad(angles)
    quat = _elementary_quat(lowered[0], angles[0])
    for axis, angle in zip(lowered[1:], angles[1:]):
        elementary = _elementary_quat(axis, angle)
        quat = _compose(quat, elementary) if intrinsic else _compose(elementary, quat)
    return quat


def _matrix_from_quat(quat: np.ndarray) -> np.ndarray:
    x, y, z, w = quat
    x2, y2, z2, w2 = x * x, y * y, z * z, w * w
    xy, zw, xz, yw, yz, xw = x * y, z * w, x * z, y * w, y * z, x * w
    return np.array([
        [x2 - y2 - z2 + w2, 2 * (xy - zw), 2 * (xz + yw)],
        [2 * (xy + zw), -x2 + y2 - z2 + w2, 2 * (yz - xw)],
        [2 * (xz - yw), 2 * (yz + xw), -x2 - y2 + z2 + w2],
    ])


def _quat_from_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (3, 3):
        raise ValueError(f"expected a 3x3 matrix, got {matrix.shape}")
    diagonal = np.diagonal(matrix)
    trace = diagonal.sum()
    decision = np.append(diagonal, trace)
    choice = int(np.argmax(decision))

    quat = np.empty(4)
    if choice != 3:
        i = choice
        j = (i + 1) % 3
        k = (j + 1) % 3
        quat[i] = 1 - trace + 2 * matrix[i, i]
        quat[j] = matrix[j, i] + matrix[i, j]
        quat[k] = matrix[k, i] + matrix[i, k]
        quat[3] = matrix[k, j] - matrix[j, k]
    else:
        quat[0] = matrix[2, 1] - matrix[1, 2]
        quat[1] = matrix[0, 2] - matrix[2, 0]
        quat[2] = matrix[1, 0] - matrix[0, 1]
        quat[3] = 1 + trace
    return quat / np.linalg.norm(quat)


def _euler_from_quat(quat: np.ndarray, seq: str, intrinsic: bool) -> np.ndarray:
    if intrinsic:
        seq = seq[::-1]
        angle_first, angle_third = 2, 0
    else:
        angle_first, angle_third = 0, 2
    if len(set(seq)) != 3:
        raise ValueError(f"symmetric sequence {seq!r} is not supported by as_euler")
    i, j, k = (_AXIS_INDEX[axis] for axis in seq)
    sign = (i - j) * (j - k) * (k - i) // 2

    vector = quat[:3]
    w = quat[3]
    a = w - vector[j]
    b = vector[i] + vector[k] * sign
    c = vector[j] + w
    d = vector[k] * sign - vector[i]

    angles = np.empty(3)
    angles[1] = 2 * np.arctan2(np.hypot(c, d), np.hypot(a, b))
    if abs(angles[1]) <= _SINGULAR:
        case = 1
    elif abs(angles[1] - np.pi) <= _SINGULAR:
        case = 2
    else:
        case = 0

    half_sum = np.arctan2(b, a)
    half_diff = np.arctan2(d, c)
    if case == 0:
        angles[angle_first] = half_sum - half_diff
        angles[angle_third] = half_sum + half_diff
    else:
        angles[2] = 0.0
        angles[0] = 2 * half_sum if case == 1 else \
            2 * half_diff * (1 if intrinsic else -1)

    angles[angle_third] *= sign
    angles[1] -= np.pi / 2
    for index in range(3):
        if angles[index] < -np.pi:
            angles[index] += 2 * np.pi
        elif angles[index] > np.pi:
            angles[index] -= 2 * np.pi
    return angles


class Rotation:

    __slots__ = ("_quat",)

    def __init__(self, quat: np.ndarray):
        self._quat = quat

    @classmethod
    def from_quat(cls, quat) -> "Rotation":
        quat = np.asarray(quat, dtype=float).reshape(-1)
        if quat.shape != (4,):
            raise ValueError("from_quat wants four numbers, scalar-last (x, y, z, w)")
        norm = np.linalg.norm(quat)
        if norm == 0.0 or not np.isfinite(norm):
            raise ValueError("a zero or non-finite quaternion is not a rotation")
        return cls(quat / norm)

    @classmethod
    def from_euler(cls, seq: str, angles, degrees: bool = False) -> "Rotation":
        return cls(_quat_from_euler(seq, angles, degrees))

    @classmethod
    def from_matrix(cls, matrix) -> "Rotation":
        return cls(_quat_from_matrix(matrix))

    def as_quat(self) -> np.ndarray:
        return self._quat.copy()

    def as_matrix(self) -> np.ndarray:
        return _matrix_from_quat(self._quat)

    def as_euler(self, seq: str, degrees: bool = False) -> np.ndarray:
        lowered, intrinsic = _parse_seq(seq, axes=(3,))
        angles = _euler_from_quat(self._quat, lowered, intrinsic)
        return np.rad2deg(angles) if degrees else angles

    def apply(self, vectors) -> np.ndarray:
        vectors = np.asarray(vectors, dtype=float)
        matrix = _matrix_from_quat(self._quat)
        if vectors.shape == (3,):
            return matrix @ vectors
        if vectors.ndim == 2 and vectors.shape[1] == 3:
            return vectors @ matrix.T
        raise ValueError(f"expected (3,) or (N, 3) vectors, got {vectors.shape}")

    def __repr__(self) -> str:
        x, y, z, w = self._quat
        return f"Rotation(quat=[{x:.6f}, {y:.6f}, {z:.6f}, {w:.6f}])"
