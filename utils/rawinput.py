import ctypes
import queue
import threading
import traceback
from ctypes import wintypes

from utils import metrics

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_INPUT = 0x00FF
HWND_MESSAGE = -3
RID_INPUT = 0x10000003
RIDEV_INPUTSINK = 0x00000100
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RI_KEY_BREAK = 0x01
RI_MOUSE_WHEEL = 0x0400
MOUSE_MOVE_ABSOLUTE = 0x01
MAPVK_VK_TO_VSC = 0
QUEUE_LIMIT = 4096

BUTTON_FLAGS = (
    (0x0001, "left", True),
    (0x0002, "left", False),
    (0x0004, "right", True),
    (0x0008, "right", False),
    (0x0010, "middle", True),
    (0x0020, "middle", False),
)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]

class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT),
                ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD),
                ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD),
                ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE),
                ("wParam", wintypes.WPARAM)]


class _MOUSEBUTTONS(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT),
                ("usButtonData", ctypes.c_short)]


class _MOUSEUNION(ctypes.Union):
    _anonymous_ = ("buttons",)
    _fields_ = [("ulButtons", wintypes.ULONG),
                ("buttons", _MOUSEBUTTONS)]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("usFlags", wintypes.USHORT),
                ("u", _MOUSEUNION),
                ("ulRawButtons", wintypes.ULONG),
                ("lLastX", wintypes.LONG),
                ("lLastY", wintypes.LONG),
                ("ulExtraInformation", wintypes.ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wintypes.USHORT),
                ("Flags", wintypes.USHORT),
                ("Reserved", wintypes.USHORT),
                ("VKey", wintypes.USHORT),
                ("Message", wintypes.UINT),
                ("ExtraInformation", wintypes.ULONG)]

class RAWHID(ctypes.Structure):
    _fields_ = [("dwSizeHid", wintypes.DWORD),
                ("dwCount", wintypes.DWORD),
                ("bRawData", ctypes.c_ubyte * 1)]


class _RAWINPUTDATA(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE),
                ("keyboard", RAWKEYBOARD),
                ("hid", RAWHID)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER),
                ("data", _RAWINPUTDATA)]


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.WORD
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.UnregisterClassW.restype = wintypes.BOOL
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE),
                                           wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                   wintypes.LPVOID,
                                   ctypes.POINTER(wintypes.UINT),
                                   wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_instances = 0
_instances_lock = threading.Lock()


class RawInputListener:

    def __init__(self, on_key=None, on_button=None, on_wheel=None, on_move=None):
        global _instances
        self.on_key = on_key
        self.on_button = on_button
        self.on_wheel = on_wheel
        self.on_move = on_move
        self._queue = queue.Queue(maxsize=QUEUE_LIMIT)
        self._hwnd = None
        self._class_name = None
        self._hinstance = None
        self._ready = threading.Event()
        self._error = None
        self._move_pending = False
        self._pump = None
        self._dispatch = None
        self._wndproc = WNDPROC(self._window_proc)
        with _instances_lock:
            _instances += 1
            self._serial = _instances

    def start(self):
        if self._pump is not None:
            return
        self._error = None
        self._ready.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._pump = threading.Thread(target=self._pump_loop,
                                      name="RawInputPump", daemon=True)
        self._pump.start()
        if not self._ready.wait(5.0):
            self._pump = None
            raise RuntimeError("raw input window did not come up")
        if self._error is not None:
            self._pump = None
            raise self._error
        self._dispatch = threading.Thread(target=self._dispatch_loop,
                                          name="RawInputDispatch", daemon=True)
        self._dispatch.start()

    def stop(self):
        pump, dispatch = self._pump, self._dispatch
        hwnd = self._hwnd
        if hwnd:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        self._queue.put(None)
        if pump is not None and pump.is_alive():
            pump.join(2.0)
        if dispatch is not None and dispatch.is_alive():
            dispatch.join(2.0)
        self._pump = None
        self._dispatch = None
        self._hwnd = None
        self._move_pending = False
        self._ready.clear()

    def _pump_loop(self):
        try:
            self._create_window()
        except OSError as exc:
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.DispatchMessageW(ctypes.byref(message))
        if self._class_name:
            user32.UnregisterClassW(self._class_name, self._hinstance)
            self._class_name = None

    def _create_window(self):
        self._hinstance = kernel32.GetModuleHandleW(None)
        name = "ExVRRawInput%d" % self._serial
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = self._hinstance
        window_class.lpszClassName = name
        if not user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._class_name = name
        hwnd = user32.CreateWindowExW(0, name, "ExVR raw input", 0, 0, 0, 0, 0,
                                      wintypes.HWND(HWND_MESSAGE), None,
                                      self._hinstance, None)
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._hwnd = hwnd
        self._register_devices(hwnd)

    def _register_devices(self, hwnd):
        devices = (RAWINPUTDEVICE * 2)()
        for slot, usage in ((0, 6), (1, 2)):
            devices[slot].usUsagePage = 1
            devices[slot].usUsage = usage
            devices[slot].dwFlags = RIDEV_INPUTSINK
            devices[slot].hwndTarget = hwnd
        if not user32.RegisterRawInputDevices(devices, 2,
                                              ctypes.sizeof(RAWINPUTDEVICE)):
            raise ctypes.WinError(ctypes.get_last_error())

    def _window_proc(self, hwnd, message, wparam, lparam):
        if message == WM_INPUT:
            try:
                self._read(lparam)
            except Exception:
                traceback.print_exc()
        elif message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        elif message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _read(self, handle):
        record = RAWINPUT()
        size = wintypes.UINT(ctypes.sizeof(record))
        read = user32.GetRawInputData(handle, RID_INPUT, ctypes.byref(record),
                                      ctypes.byref(size),
                                      ctypes.sizeof(RAWINPUTHEADER))
        if read == 0 or read == 0xFFFFFFFF:
            return
        if record.header.dwType == RIM_TYPEKEYBOARD:
            self._keyboard(record.data.keyboard)
        elif record.header.dwType == RIM_TYPEMOUSE:
            self._mouse(record.data.mouse)

    def _keyboard(self, record):
        vk = record.VKey
        if vk == 0 or vk == 0xFF:
            return
        scan_code = record.MakeCode
        if not scan_code:
            scan_code = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
            if not scan_code:
                return
        self._push(("key", scan_code, not record.Flags & RI_KEY_BREAK))

    def _mouse(self, record):
        flags = record.usButtonFlags
        if flags:
            for mask, name, pressed in BUTTON_FLAGS:
                if flags & mask:
                    self._push(("button", name, pressed))
            if flags & RI_MOUSE_WHEEL and record.usButtonData:
                self._push(("wheel", record.usButtonData))
        moved = record.lLastX or record.lLastY
        if (moved or record.usFlags & MOUSE_MOVE_ABSOLUTE) \
                and not self._move_pending:
            self._move_pending = self._push(("move",))

    def _push(self, event):
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            metrics.count("rawinput.dropped")
            return False
        return True

    def _dispatch_loop(self):
        while True:
            event = self._queue.get()
            if event is None:
                return
            try:
                self._deliver(event)
            except Exception:
                traceback.print_exc()

    def _deliver(self, event):
        kind = event[0]
        if kind == "key":
            if self.on_key is not None:
                self.on_key(event[1], event[2])
        elif kind == "button":
            if self.on_button is not None:
                self.on_button(event[1], event[2])
        elif kind == "wheel":
            if self.on_wheel is not None:
                self.on_wheel(event[1])
        elif kind == "move":
            self._move_pending = False
            if self.on_move is not None:
                point = wintypes.POINT()
                if user32.GetCursorPos(ctypes.byref(point)):
                    self.on_move(point.x, point.y)
