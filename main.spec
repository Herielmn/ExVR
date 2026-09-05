# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs


ROOT = Path.cwd()


def add_tree(folder, exclude_suffixes=(), exclude_names=(), exclude_dirs=()):
    root = ROOT / folder
    entries = []
    if not root.exists():
        return entries
    lowered = {name.lower() for name in exclude_names}
    skipped = {name.lower() for name in exclude_dirs}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if skipped & {part.lower() for part in path.relative_to(ROOT).parts[:-1]}:
            continue
        if path.suffix.lower() in exclude_suffixes:
            continue
        if path.name.lower() in lowered:
            continue
        entries.append((str(path), str(path.parent.relative_to(ROOT))))
    return entries


SECRET_SUFFIXES = (".pem",)
SECRET_NAMES = ("pairing.json",)

RUNTIME_DIRS = ("logs", "ssl")

datas = []
for folder in ("settings", "templates", "models"):
    datas += add_tree(folder, exclude_suffixes=SECRET_SUFFIXES,
                      exclude_names=SECRET_NAMES, exclude_dirs=RUNTIME_DIRS)
datas += add_tree("drivers", exclude_suffixes=(".pdb", ".lib", ".exp"))


def fp16_models():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from models_fp16 import build_tree
    except ImportError as exc:
        raise SystemExit(
            "onnx is needed to convert the models for the release: "
            "pip install -r requirements-dev.txt") from exc

    tree = ROOT / "build" / "modules-fp16"
    rows = build_tree(tree)
    shipped = {name for name, _src, _dst, _stats in rows}
    expected = {path.name for path in (ROOT / "modules").iterdir() if path.is_file()}
    assert shipped == expected, f"the fp16 tree is missing {expected - shipped}"
    source = sum(src for _n, src, _d, _s in rows)
    built = sum(dst for _n, _s2, dst, _s in rows)
    assert built < 0.6 * source, (
        f"the fp16 tree is {built:,} B against {source:,} B; the conversion did "
        "not happen")
    return [(str(tree / name), "modules") for name, _src, _dst, _stats in rows]


datas += fp16_models()

_shipped = {Path(src).name.lower() for src, _dest in datas}
assert not (_shipped & set(SECRET_NAMES)), "a per-install secret reached the bundle"
assert not any(n.endswith(SECRET_SUFFIXES) for n in _shipped), \
    "a .pem reached the bundle"


def videoio_plugin():
    import cv2
    folder = Path(cv2.__file__).parent
    if (folder / "__init__.py").exists():
        return []
    plugins = [(str(dll), ".") for dll in folder.glob("opencv_videoio_ffmpeg*.dll")]
    assert plugins, f"no FFmpeg plugin DLL beside {folder}; IP cameras would break"
    return plugins


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=collect_dynamic_libs("onnxruntime") + videoio_plugin(),
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "torchvision",
        "matplotlib",
        "PIL",
        "networkx",
        "sympy",
        "pandas",
        "fsspec",
        "tracker.face.tongue_model",
        "tracker.hand.hand_depth_model",
        "sklearn",
        "joblib",
        "scipy",
        "onnx",
    ],
    noarchive=False,
    optimize=0,
)
BINARY_EXCLUDES = {"opengl32sw.dll"}
a.binaries = [b for b in a.binaries if Path(b[0]).name.lower() not in BINARY_EXCLUDES]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ExVR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=['logo\\logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ExVR',
)
