"""Records what you do (typing, key presses, clicks, app switches) as macro steps.

The low-level hooks only queue cheap facts; a worker thread turns them into
steps so Windows never drops the hooks for being slow. Gem's own input and
windows, the talk key and Gem's hotkeys are never recorded, nothing typed in
a sign-in or password window is kept, and recordings stay in memory only.
"""
import ctypes
import ctypes.wintypes as wt
import logging
import os
import queue
import re
import threading
import time

from .runtime import svc
from .winapi import MODIFIERS, VK, foreground_window, key_code, toggle_state, vk_name, window_at, window_class, \
    window_pid, window_rect_physical, window_title

log = logging.getLogger("gem.recorder")

WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_LBUTTONDOWN, WM_RBUTTONDOWN = 0x0201, 0x0204
WM_QUIT, WM_USER = 0x0012, 0x0400
LLKHF_INJECTED, LLMHF_INJECTED = 0x10, 0x01

MAX_STEPS = 200
GAP_S = 1.5          # this much quiet ends a typed run and earns a wait step
HUSH_S = 3.0         # after a spoken command Gem itself may change the app in front
POLL_S = 0.15

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
_user32.SetWindowsHookExW.restype = wt.HHOOK
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
_user32.CallNextHookEx.restype = LRESULT
_user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
_user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
_user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
_user32.GetForegroundWindow.restype = wt.HWND
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_user32.GetKeyboardLayout.restype = wt.HKL
_user32.GetKeyboardLayout.argtypes = [wt.DWORD]
_user32.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_ubyte), wt.LPWSTR, ctypes.c_int, wt.UINT,
                                wt.HKL]
_user32.GetDoubleClickTime.restype = wt.UINT
_kernel32.GetModuleHandleW.restype = wt.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


# Parts of Windows itself: clicks there aren't recorded (app switches come from polling).
_SHELL_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "NotifyIconOverflowWindow",
                  "TopLevelWindowForOverflowXamlIsland", "Windows.UI.Core.CoreWindow", "TaskListThumbnailWnd",
                  "XamlExplorerHostIslandWindow", "MultitaskingViewFrame"}
_SKIP_VKS = {0x14, 0x90, 0x91,                                      # Caps Lock (Gem's key), Num Lock, Scroll Lock
             0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}   # modifiers on their own
# Keys that never type text: enter, tab, esc, delete, arrows, home/end, page up/down, insert, backspace, menu, F1-F24.
_SPECIAL_VKS = {0x0D, 0x09, 0x1B, 0x2E, 0x25, 0x26, 0x27, 0x28, 0x24, 0x23, 0x21, 0x22, 0x2D, 0x08, 0x5D} \
    | set(range(0x70, 0x88))
_HELD = (("ctrl", 0x11), ("shift", 0x10), ("alt", 0x12), ("win", 0x5B), ("win", 0x5C))
# Window switching shows up as a "switch to" step instead.
_SWITCHER_CHORDS = {"alt+tab", "shift+alt+tab", "ctrl+alt+tab", "win+tab", "alt+esc", "shift+alt+esc"}
_PRIVATE = re.compile(r"password|passcode|pass code|sign ?in|log ?in|login|verify|verification|2fa|otp|one-time|bank|"
                      r"paypal|1password|bitwarden|lastpass|keepass|dashlane|credit card|card number|cvv", re.I)


def _short(text, n=40):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _seconds(gap):
    """Wait length for a gap: at most 10 s, to the nearest half second ("2", "2.5")."""
    return "%g" % (round(min(gap, 10.0) * 2) / 2)


class _Steps:
    """Turns recorded input into macro steps. Pure logic, no Windows calls; t is in seconds."""

    def __init__(self, double_s=0.5, limit=MAX_STEPS):
        self.steps = []
        self.notes = []
        self.double_s = double_s
        self.limit = limit
        self.full = False
        self._app = ""             # app in front, as the steps last saw it
        self._last_at = None       # when the last step ended
        self._hush_until = 0.0
        self._buf = ""             # typed text not yet written as a step
        self._buf_app = ""
        self._buf_start = 0.0
        self._buf_at = 0.0
        self._press = None         # (chord, count, step index) of the last press, for "3 times"
        self._click = None         # (x, y, t, step index) of the last left click, for double clicks

    def text(self, chars, app, t, title=""):
        if self.full or self._private(title, app):
            return
        self._enter(app, t)
        if self._buf and (app != self._buf_app or t - self._buf_at >= GAP_S):
            self._flush()
        for ch in chars:
            if not ch.isprintable():
                continue
            if not self._buf:
                self._buf_app, self._buf_start = app, t
            self._buf += ch
            self._buf_at = t

    def key(self, chord, app, t, title=""):
        if self.full:
            return
        if chord == ["backspace"]:
            if self._buf and self._buf_app == app:
                self._buf = self._buf[:-1]
                self._buf_at = t
                return
            if self._private(title, app):    # it edits text we never recorded
                return
        name = "+".join([m for m in MODIFIERS if m in chord] + [k for k in chord if k not in MODIFIERS])
        self._enter(app, t)
        self._flush()
        last = self._press
        if last and last[0] == name and last[2] == len(self.steps) - 1 and t - self._last_at < GAP_S:
            self._press = (name, last[1] + 1, last[2])
            self.steps[-1] = "press %s %d times" % (name, last[1] + 1)
            self._last_at = t
            return
        if self._add("press " + name, t):
            self._press = (name, 1, len(self.steps) - 1)

    def click(self, kind, px, py, app, t, x=0, y=0):
        """kind is "left" or "right"; px, py are percent of the window; x, y are screen pixels."""
        if self.full:
            return
        self._enter(app, t)
        self._flush()
        last = self._click
        if kind == "left" and last and last[3] == len(self.steps) - 1 and t - last[2] <= self.double_s \
                and abs(x - last[0]) <= 4 and abs(y - last[1]) <= 4:
            self.steps[-1] = "double " + self.steps[-1]
            self._click = None
            self._last_at = t
            return
        step = "%s at %.1f%% %.1f%%" % ("right click" if kind == "right" else "click", px, py)
        if self._add(step + (" in " + app if app else ""), t):
            self._click = (x, y, t, len(self.steps) - 1) if kind == "left" else None

    def switch(self, app, t):
        if self.full or not app or app == self._app:
            return
        self._app = app
        if t < self._hush_until:
            return
        self._flush()
        self._add("switch to " + app, t)

    def command(self, text, t):
        """A spoken Gem command: kept verbatim, and Gem's own app switches right after aren't recorded."""
        text = (text or "").strip()
        if self.full or not text:
            return
        self._flush()
        self._add(text, t)
        self._hush_until = t + HUSH_S

    def tick(self, t):
        if self._buf and t - self._buf_at >= GAP_S:
            self._flush()

    def finish(self):
        """(steps, notes) with any typing written out and no wait at the end."""
        self._flush()
        while self.steps and self.steps[-1].startswith("wait "):
            self.steps.pop()
        return list(self.steps), list(self.notes)

    def _enter(self, app, t):
        if app and app != self._app:
            self.switch(app, t)

    def _flush(self):
        if self._buf:
            text, self._buf = self._buf, ""
            self._add("type " + text, self._buf_start, self._buf_at)

    def _add(self, step, start, end=None):
        wait = self._last_at is not None and start - self._last_at >= GAP_S
        if len(self.steps) + (2 if wait else 1) > self.limit:
            self.full = True
            self._buf = ""
            self.notes.append("I stopped recording at %d steps." % self.limit)
            return False
        if wait:
            self.steps.append("wait %s seconds" % _seconds(start - self._last_at))
        self.steps.append(step)
        self._last_at = start if end is None else end
        return True

    def _private(self, title, app):
        """True (with a note, once per window) when what's typed here might be a password."""
        if not _PRIVATE.search(title or "") and not _PRIVATE.search(app or ""):
            return False
        note = "I didn't record what you typed in “%s”." % _short(title or app)
        if note not in self.notes:
            self.notes.append(note)
        return True


def _translate(vk, scan, mods, caps, hwnd):
    """The text a key-down types with these modifiers in that window's keyboard layout ("" if none)."""
    state = (ctypes.c_ubyte * 256)()
    for name, vks in (("shift", (0x10, 0xA0)), ("ctrl", (0x11, 0xA2)), ("alt", (0x12, 0xA4))):
        if name in mods:
            for v in vks:
                state[v] = 0x80
    if caps:
        state[0x14] = 0x01
    buf = ctypes.create_unicode_buffer(8)
    layout = _user32.GetKeyboardLayout(_user32.GetWindowThreadProcessId(hwnd, None))
    n = _user32.ToUnicodeEx(vk, scan, state, buf, 8, 0x4, layout)     # 0x4: leave the keyboard state alone
    if n < 1:
        return ""
    chars = buf[:n]
    return chars if chars.isprintable() else ""


def _hotkey(text):
    """'ctrl+alt+space' -> ({'ctrl', 'alt'}, {VK codes of the other keys})."""
    parts = [{"control": "ctrl", "windows": "win"}.get(p, p) for p in re.split(r"\s*\+\s*", (text or "").lower())]
    mods = {p for p in parts if p in MODIFIERS}
    keys = {key_code(p) for p in parts if p and p not in MODIFIERS} - {None}
    return mods, keys


class Recorder:
    def __init__(self, on_limit=None, max_seconds=600):
        self.on_limit = on_limit              # called once, on the worker thread, when time runs out
        self.max_seconds = max_seconds

        self._lock = threading.Lock()
        self._steps = None
        self._result = ([], [])
        self._events = queue.Queue()
        self._running = False
        self._session = 0
        self._started = 0.0
        self._stopped = 0.0
        self._limited = False
        self._thread_id = None
        self._threads = []
        self._hotkeys = []
        self._names = {}                      # pid -> app name
        self._key_proc = HOOKPROC(self._on_key)       # keep references or they get collected
        self._mouse_proc = HOOKPROC(self._on_mouse)

    def start(self):
        """Starts recording; the hooks go in on their own thread."""
        if self._running:
            return
        self._session += 1
        self._steps = _Steps(double_s=_user32.GetDoubleClickTime() / 1000.0)
        self._result = ([], [])
        self._events = queue.Queue()
        self._names = {}
        self._limited = False
        self._thread_id = None
        keys = svc.config["keys"] if svc.config else {}
        self._hotkeys = [_hotkey(keys.get(name, "")) for name in ("command_bar", "panic")]
        self._started = time.monotonic()
        self._running = True
        hwnd = foreground_window()
        if self._usable(hwnd):
            self._steps.switch(self._app_name(hwnd), self._started)
        session = self._session
        self._threads = [threading.Thread(target=self._hook_thread, args=(session,), name="rec-hook", daemon=True),
                         threading.Thread(target=self._worker, args=(session,), name="rec-events", daemon=True)]
        for thread in self._threads:
            thread.start()

    def stop(self):
        """Stops recording: (steps, notes). Safe to call more than once."""
        if self._end():
            with self._lock:
                if self._steps:
                    self._result = self._steps.finish()
                self._steps = None
        return self._result

    def cancel(self):
        """Stops recording and forgets it."""
        self._end()
        with self._lock:
            self._steps = None
            self._result = ([], [])

    def active(self):
        return self._running

    def elapsed(self):
        if not self._started:
            return 0.0
        return (time.monotonic() if self._running else self._stopped) - self._started

    def add_command(self, text):
        """A Gem command spoken while recording; it becomes a step as said."""
        with self._lock:
            if self._steps:
                self._steps.command(text, time.monotonic())

    def _end(self):
        if not self._running:
            return False
        self._running = False
        self._stopped = time.monotonic()
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(1.0)
        return True

    # ── Hooks (run on the hook thread; must stay fast) ───────────────────────

    def _on_key(self, code, wparam, lparam):
        if code == 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not (kb.flags & LLKHF_INJECTED) and kb.vkCode not in _SKIP_VKS and not _talking():
                mods = tuple(name for name, vk in _HELD if _user32.GetAsyncKeyState(vk) & 0x8000)
                self._events.put(("key", time.monotonic(), kb.vkCode, kb.scanCode, mods, toggle_state(VK["caps"]),
                                  _user32.GetForegroundWindow()))
        return _user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_mouse(self, code, wparam, lparam):
        if code == 0 and wparam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
            ms = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if not (ms.flags & LLMHF_INJECTED) and not _talking():
                self._events.put(("click", time.monotonic(), wparam, ms.pt.x, ms.pt.y))
        return _user32.CallNextHookEx(None, code, wparam, lparam)

    def _hook_thread(self, session):
        msg = wt.MSG()
        _user32.PeekMessageW(ctypes.byref(msg), None, WM_USER, WM_USER, 0)   # make the message queue exist first
        self._thread_id = _kernel32.GetCurrentThreadId()
        module = _kernel32.GetModuleHandleW(None)
        hooks = [_user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._key_proc, module, 0),
                 _user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, module, 0)]
        if not all(hooks):
            log.error("Could not install recording hooks (error %d)", ctypes.get_last_error())
        try:
            while self._running and self._session == session \
                    and _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hook in hooks:
                if hook:
                    _user32.UnhookWindowsHookEx(hook)

    # ── Turning events into steps ───────────────────────────────────────────

    def _worker(self, session):
        events = self._events
        next_poll = 0.0
        while self._running and self._session == session:
            try:
                event = events.get(timeout=POLL_S)
            except queue.Empty:
                event = None
            try:
                if event:
                    self._handle(event)
                now = time.monotonic()
                if now >= next_poll and events.empty():
                    next_poll = now + POLL_S
                    self._poll(now)
            except Exception:
                log.exception("Recording failed to handle an event")
        while not events.empty():                 # what came in just before the stop
            try:
                self._handle(events.get_nowait())
            except Exception:
                log.exception("Recording failed to handle an event")

    def _handle(self, event):
        if event[0] == "key":
            _, t, vk, scan, mods, caps, hwnd = event
            if not self._usable(hwnd) or any(vk in keys and hk_mods <= set(mods) for hk_mods, keys in self._hotkeys):
                return
            what = self._classify(vk, scan, mods, caps, hwnd)
            if not what or (what[0] == "key" and "+".join(what[1]) in _SWITCHER_CHORDS):
                return
            app, title = self._app_name(hwnd), window_title(hwnd)
            with self._lock:
                if self._steps:
                    if what[0] == "text":
                        self._steps.text(what[1], app, t, title)
                    else:
                        self._steps.key(what[1], app, t, title)
            return
        _, t, button, x, y = event
        root = window_at(x, y)
        if not self._usable(root):
            return
        if window_class(root) == "#32768":           # a pop-up menu isn't in the same spot next time
            with self._lock:
                note = "I didn't record clicks in pop-up menus. Use keys or a “click …” step for those."
                if self._steps and note not in self._steps.notes:
                    self._steps.notes.append(note)
            return
        left, top, right, bottom = window_rect_physical(root)
        if right <= left or bottom <= top:
            return
        px = min(max(round((x - left) / (right - left) * 100, 1), 0.0), 100.0)
        py = min(max(round((y - top) / (bottom - top) * 100, 1), 0.0), 100.0)
        app = self._app_name(root)
        with self._lock:
            if self._steps:
                self._steps.click("right" if button == WM_RBUTTONDOWN else "left", px, py, app, t, x, y)

    @staticmethod
    def _classify(vk, scan, mods, caps, hwnd):
        """A key-down as ("text", chars) or ("key", chord), or None to skip it."""
        ctrl, alt = "ctrl" in mods, "alt" in mods
        if "win" not in mods and ctrl == alt and (ctrl or vk not in _SPECIAL_VKS):
            chars = _translate(vk, scan, mods, caps, hwnd)       # Ctrl+Alt together is AltGr when it types
            if chars:
                return "text", chars
            if not ctrl:
                return None                      # dead keys, media keys
        name = vk_name(vk)
        if not name:
            return None
        if name == "backspace" and mods == ("shift",):
            mods = ()
        return "key", [m for m in MODIFIERS if m in mods] + [name]

    def _poll(self, now):
        hwnd = foreground_window()
        app = self._app_name(hwnd) if self._usable(hwnd) else ""
        with self._lock:
            if self._steps:
                self._steps.switch(app, now)
                self._steps.tick(now)
        if self.on_limit and not self._limited and self.elapsed() >= self.max_seconds:
            self._limited = True
            try:
                self.on_limit()
            except Exception:
                log.exception("Recording time limit handler failed")

    @staticmethod
    def _usable(hwnd):
        """A window whose input belongs in a recording: not Gem's own, not part of Windows itself."""
        return bool(hwnd) and window_pid(hwnd) != os.getpid() and window_class(hwnd) not in _SHELL_CLASSES

    def _app_name(self, hwnd):
        pid = window_pid(hwnd)
        if pid not in self._names:
            from .skills.apps import friendly_name
            self._names[pid] = friendly_name(hwnd)
        return self._names[pid]


def _talking():
    """Caps Lock is held: the user is talking to Gem, not doing the task."""
    return bool(svc.state and svc.state.key_held)
