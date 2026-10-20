"""Thin ctypes wrappers for the Windows APIs Gem needs."""
import ctypes
import ctypes.wintypes as wt
import os
import time
import uuid

import psutil

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32")

ULONG_PTR = ctypes.c_size_t

user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindow.restype = wt.HWND
user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]

# ── Keyboard input ────────────────────────────────────────────────────────────

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "enter": 0x0D, "tab": 0x09,
    "esc": 0x1B, "backspace": 0x08, "delete": 0x2E, "space": 0x20, "left": 0x25,
    "up": 0x26, "right": 0x27, "down": 0x28, "home": 0x24, "end": 0x23,
    "play_pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
    "vol_mute": 0xAD, "vol_down": 0xAE, "vol_up": 0xAF,
    "caps": 0x14, "num": 0x90, "scroll": 0x91,
}
EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x24, 0x23, 0x2E, 0x5B, 0xB3, 0xB0, 0xB1, 0xB2, 0xAD, 0xAE, 0xAF}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def _key_input(vk=0, scan=0, flags=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def key_down(vk):
    _send([_key_input(vk, flags=KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)])


def key_up(vk):
    flags = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)
    _send([_key_input(vk, flags=flags)])


def press(*names):
    """Press a chord like press("ctrl", "c") or a single key like press("next")."""
    vks = [VK[n] if isinstance(n, str) and n in VK else (ord(n.upper()) if isinstance(n, str) else n) for n in names]
    for vk in vks:
        key_down(vk)
    for vk in reversed(vks):
        key_up(vk)


def release_modifiers():
    for name in ("ctrl", "shift", "alt", "win"):
        if user32.GetAsyncKeyState(VK[name]) & 0x8000:
            key_up(VK[name])
    for vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5C):
        if user32.GetAsyncKeyState(vk) & 0x8000:
            key_up(vk)


def type_text(text):
    """Type text into the focused window as Unicode keystrokes."""
    inputs = []
    for ch in text:
        if ch == "\n":
            inputs += [_key_input(VK["enter"]), _key_input(VK["enter"], flags=KEYEVENTF_KEYUP)]
            continue
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):
            code = int.from_bytes(data[i:i + 2], "little")
            inputs.append(_key_input(0, code, KEYEVENTF_UNICODE))
            inputs.append(_key_input(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    for i in range(0, len(inputs), 200):
        _send(inputs[i:i + 200])
        time.sleep(0.01)


def toggle_state(vk):
    return bool(user32.GetKeyState(vk) & 1)


def shift_held():
    return bool(user32.GetAsyncKeyState(VK["shift"]) & 0x8000)


# ── Clipboard ─────────────────────────────────────────────────────────────────

def get_clipboard():
    import win32clipboard
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(13):   # CF_UNICODETEXT
                    return win32clipboard.GetClipboardData(13)
                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.05)
    return ""


def set_clipboard(text):
    import win32clipboard
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(13, text)
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.05)
    return False


def copy_selection(timeout=0.6):
    """Copy whatever is selected in the focused app and return it."""
    before = user32.GetClipboardSequenceNumber()
    release_modifiers()
    press("ctrl", "c")
    end = time.time() + timeout
    while time.time() < end:
        if user32.GetClipboardSequenceNumber() != before:
            time.sleep(0.03)
            return get_clipboard()
        time.sleep(0.02)
    return ""


def paste_text(text):
    old = get_clipboard()
    set_clipboard(text)
    release_modifiers()
    press("ctrl", "v")
    time.sleep(0.25)
    if old:
        set_clipboard(old)


# ── Windows ───────────────────────────────────────────────────────────────────

WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
SW_RESTORE, SW_MINIMIZE, SW_MAXIMIZE = 9, 6, 3
WM_CLOSE = 0x0010


def foreground_window():
    return user32.GetForegroundWindow()


def window_title(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def window_process_name(hwnd):
    try:
        return psutil.Process(window_pid(hwnd)).name().lower()
    except Exception:
        return ""


def top_windows():
    """Visible, titled top-level windows as (hwnd, title, process name)."""
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0 \
                and not user32.GetWindow(hwnd, 4):   # GW_OWNER: skip owned popups
            found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return [(h, window_title(h), window_process_name(h)) for h in found]


def focus_window(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # Windows only lets the foreground app hand over focus; a synthetic Alt
    # press makes us count as having recent input.
    key_down(VK["alt"])
    key_up(VK["alt"])
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)


def show_window(hwnd, cmd):
    user32.ShowWindow(hwnd, cmd)


def close_window(hwnd):
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def window_rect_physical(hwnd):
    """Window bounds in physical pixels, regardless of display scaling."""
    rect = wt.RECT()
    old = None
    try:
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        old = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass
    try:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    finally:
        if old:
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))
    return rect.left, rect.top, rect.right, rect.bottom


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


user32.MonitorFromWindow.restype = wt.HANDLE
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]


def foreground_is_fullscreen(ignore_pid=None):
    """True when the window in front covers its whole monitor (video, games)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or (ignore_pid and window_pid(hwnd) == ignore_pid):
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        return False
    info = MONITORINFO(ctypes.sizeof(MONITORINFO))
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
        return False
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    m = info.rcMonitor
    return rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom


# ── Misc ──────────────────────────────────────────────────────────────────────

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def idle_seconds():
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return (kernel32.GetTickCount() - info.dwTime) / 1000.0


def lock_workstation():
    user32.LockWorkStation()


def message_box(text, title="Gem"):
    user32.MessageBoxW(None, text, title, 0x40)


_FOLDER_IDS = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


def known_folder(name):
    """Real path of Desktop/Documents/Downloads/... (follows OneDrive redirection)."""
    fid = _FOLDER_IDS.get(name)
    fallback = os.path.join(os.path.expanduser("~"), name.capitalize())
    if not fid:
        return fallback
    try:
        g = GUID.from_buffer_copy(uuid.UUID(fid).bytes_le)
        path = ctypes.c_wchar_p()
        if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(path)) == 0:
            value = path.value
            ole32.CoTaskMemFree(path)
            return value
    except Exception:
        pass
    return fallback
