from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from utils.paths import app_path  # noqa: E402

FEATURE_PKL = app_path("models", "hand_feature_model.pkl")
REGRESSION_PKL = app_path("models", "hand_regression_model.pkl")
NPZ = app_path("models", "hand_depth.npz")


def load_from_pickles():
    import joblib

    feature_model = joblib.load(FEATURE_PKL)
    regression_model = joblib.load(REGRESSION_PKL)
    return (
        feature_model.powers_.astype(np.int16),
        regression_model.coef_.astype(np.float64),
        float(regression_model.intercept_),
    )


def load_from_npz(path=NPZ):
    with np.load(path) as data:
        return (
            data["powers"].astype(np.int16),
            data["coef"].astype(np.float64),
            float(data["intercept"]),
        )


def predict(powers, coef, intercept, data):
    values = np.asarray(data, dtype=np.float64)
    monomials = np.prod(values[:, None, :] ** powers[None, :, :], axis=2)
    return monomials @ coef + intercept


def main() -> int:
    print(f"reading  {FEATURE_PKL.name} ({FEATURE_PKL.stat().st_size} B)")
    print(f"reading  {REGRESSION_PKL.name} ({REGRESSION_PKL.stat().st_size} B)")
    powers, coef, intercept = load_from_pickles()
    print(f"  powers    {powers.shape} {powers.dtype}")
    print(f"  coef      {coef.shape} {coef.dtype}")
    print(f"  intercept {intercept!r}")

    np.savez(NPZ, powers=powers, coef=coef, intercept=np.float64(intercept))
    print(f"wrote    {NPZ.name} ({NPZ.stat().st_size} B)")

    powers2, coef2, intercept2 = load_from_npz()

    assert powers2.dtype == powers.dtype, (powers2.dtype, powers.dtype)
    assert coef2.dtype == coef.dtype, (coef2.dtype, coef.dtype)
    assert np.array_equal(powers2, powers), "powers differ"
    assert np.array_equal(coef2, coef), "coef differ"
    assert intercept2 == intercept, (intercept2, intercept)
    print("arrays   identical (dtype, shape, every element)")

    n_features = powers.shape[1]
    rng = np.random.default_rng(0)
    cases = {
        "random uniform": rng.random((256, n_features)),
        "random normal": rng.standard_normal((256, n_features)),
        "zeros": np.zeros((1, n_features)),
        "ones": np.ones((1, n_features)),
        "large": rng.standard_normal((64, n_features)) * 1e3,
        "tiny": rng.standard_normal((64, n_features)) * 1e-6,
    }
    for name, x in cases.items():
        a = predict(powers, coef, intercept, x)
        b = predict(powers2, coef2, intercept2, x)
        same_bits = a.tobytes() == b.tobytes()
        assert np.array_equal(a, b, equal_nan=True), f"predict differs on {name}"
        assert same_bits, f"predict not bit-identical on {name}"
        print(f"predict  bit-identical on {name:14s} ({x.shape[0]} rows)")

    print("\nOK - hand_depth.npz reproduces the pickled models exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
