"""Caps Lock as Gem's key, plus the global hotkeys.

Hold    push-to-talk (or push-to-mute in always-listening mode)
Tap     stop Gem talking
3 taps  switch between push-to-talk and always-listening
Shift+Caps Lock still toggles real capitals.

The low-level hook swallows Caps Lock so the real caps state never changes.
The callback only queues events; everything else runs on a worker thread so
Windows never drops the hook for being slow.
"""
import ctypes
import ctypes.wintypes as wt
import logging
import queue
import threading
import time

from .winapi import VK, shift_held, toggle_state

log = logging.getLogger("gem.keys")

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_APP_REINSTALL = 0x8000 + 1
LLKHF_INJECTED = 0x10

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
_kernel32.GetModuleHandleW.restype = wt.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class TalkKey:
    def __init__(self, on_press, on_release, on_tap, on_triple_tap, hold_ms=250, triple_tap_ms=900):
        self.on_press = on_press
        self.on_release = on_release          # on_release(was_tap: bool)
        self.on_tap = on_tap
        self.on_triple_tap = on_triple_tap
        self.hold_s = hold_ms / 1000.0
        self.triple_s = triple_tap_ms / 1000.0

        self._events = queue.Queue()
        self._down = False
        self._passthrough = False
        self._expected_caps = None
        self._hook = None
        self._thread_id = None
        self._proc = HOOKPROC(self._hook_proc)   # keep a reference or it gets collected
        self._taps = []
        self.last_user_key = 0.0              # time.monotonic() of the user's last real key press (not Caps Lock)

    def start(self):
        threading.Thread(target=self._hook_thread, name="caps-hook", daemon=True).start()
        threading.Thread(target=self._worker, name="caps-events", daemon=True).start()
        threading.Thread(target=self._watchdog, name="caps-watchdog", daemon=True).start()

    # ── Hook (runs on the hook thread; must stay fast) ───────────────────────

    def _hook_proc(self, code, wparam, lparam):
        if code == 0:
            kb = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.vkCode != VK["caps"] and not (kb.flags & LLKHF_INJECTED) and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self.last_user_key = time.monotonic()     # a running macro stops when you start typing
            if kb.vkCode == VK["caps"] and not (kb.flags & LLKHF_INJECTED):
                if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    if self._passthrough or (not self._down and shift_held()):
                        self._passthrough = True
                        return _user32.CallNextHookEx(None, code, wparam, lparam)
                    if not self._down:
                        self._down = True
                        self._events.put(("down", time.monotonic()))
                    return 1
                if wparam in (WM_KEYUP, WM_SYSKEYUP):
                    if self._passthrough:
                        self._passthrough = False
                        self._expected_caps = None      # real caps changed on purpose
                        return _user32.CallNextHookEx(None, code, wparam, lparam)
                    if self._down:
                        self._down = False
                        self._events.put(("up", time.monotonic()))
                    return 1
        return _user32.CallNextHookEx(None, code, wparam, lparam)

    @staticmethod
    def _toggle_real_caps():
        # Injected, so our own hook lets it through.
        _user32.keybd_event(VK["caps"], 0x3A, 0, 0)
        _user32.keybd_event(VK["caps"], 0x3A, 2, 0)

    def _install(self, first=False):
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, _kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            log.error("Could not install keyboard hook (error %d)", ctypes.get_last_error())
        if first:
            # Gem owns Caps Lock, so real caps starts off. Otherwise caps left on
            # while Gem wasn't running could never be turned off with Caps Lock.
            if toggle_state(VK["caps"]):
                self._toggle_real_caps()
            self._expected_caps = False

    def _hook_thread(self):
        self._thread_id = _kernel32.GetCurrentThreadId()
        self._install(first=True)
        msg = wt.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_APP_REINSTALL:
                log.warning("Caps Lock hook was dropped by Windows; reinstalling")
                self._install()
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    def _watchdog(self):
        """If Caps Lock turned on without Shift, Windows removed our hook: undo it and re-hook.

        It only ever turns caps off, never back on, so caps can't get stuck on.
        """
        while True:
            time.sleep(2)
            if self._thread_id is None or self._passthrough:
                continue
            actual = toggle_state(VK["caps"])
            expected = self._expected_caps
            if expected is None:                 # just toggled on purpose with Shift+Caps Lock
                self._expected_caps = actual
            elif actual and not expected:
                self._toggle_real_caps()
                _user32.PostThreadMessageW(self._thread_id, WM_APP_REINSTALL, 0, 0)
            elif not actual and expected:        # turned off some other way: accept it
                self._expected_caps = False

    # ── Gesture recognition ─────────────────────────────────────────────────

    def _worker(self):
        down_at = 0.0
        while True:
            kind, t = self._events.get()
            try:
                if kind == "down":
                    down_at = t
                    self.on_press()
                    continue
                was_tap = (t - down_at) < self.hold_s
                self.on_release(was_tap)
                if not was_tap:
                    self._taps.clear()
                    continue
                self._taps = [x for x in self._taps if t - x < self.triple_s] + [t]
                if len(self._taps) >= 3:
                    self._taps.clear()
                    self.on_triple_tap()
                else:
                    self.on_tap()
            except Exception:
                log.exception("Caps Lock handler failed")


def register_hotkeys(command_bar, on_command_bar, panic, on_panic):
    """Global combos via the keyboard library (separate from the Caps hook)."""
    try:
        import keyboard
    except ImportError:
        log.warning("keyboard library missing; hotkeys disabled")
        return
    for combo, cb in ((command_bar, on_command_bar), (panic, on_panic)):
        if not combo:
            continue
        try:
            keyboard.add_hotkey(combo, cb, suppress=False)
            log.info("Hotkey %s registered", combo)
        except Exception as e:
            log.error("Could not register hotkey %s: %s", combo, e)
