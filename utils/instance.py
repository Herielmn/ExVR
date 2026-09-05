from __future__ import annotations

import ctypes
from ctypes import wintypes

NAME = "Local\\ExVR-Next-core"
ERROR_ALREADY_EXISTS = 183

_held = None


def claim(name: str = NAME) -> bool:
    global _held
    if _held is not None:
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL,
                                          wintypes.LPCWSTR)
        handle = kernel32.CreateMutexW(None, False, name)
    except OSError:
        return True
    if not handle:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _held = handle
    return True
