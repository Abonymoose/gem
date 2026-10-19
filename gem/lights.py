"""Num / Caps / Scroll Lock lights as Gem's status display.

Windows lets us set the keyboard LEDs directly through the keyboard class
driver without touching the real lock states, so typing never turns into
capitals. Anything that fails here just turns the lights into a no-op.
"""
import ctypes
import ctypes.wintypes as wt
import logging
import queue
import threading
import time

from .winapi import VK, toggle_state

log = logging.getLogger("gem.lights")

SCROLL, NUM, CAPS = 1, 2, 4
ALL = SCROLL | NUM | CAPS

IOCTL_KEYBOARD_QUERY_INDICATORS = 0x000B0040
IOCTL_KEYBOARD_SET_INDICATORS = 0x000B0008

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.restype = wt.HANDLE
_k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
_k32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, wt.LPVOID, wt.DWORD, wt.LPVOID, wt.DWORD,
                                 ctypes.POINTER(wt.DWORD), wt.LPVOID]
_INVALID = wt.HANDLE(-1).value


class _Indicators(ctypes.Structure):
    _fields_ = [("UnitId", wt.USHORT), ("LedFlags", wt.USHORT)]


# Left-to-right order of the lights on most keyboards.
_SWEEP = [NUM, NUM | CAPS, ALL]


class KeyboardLights:
    def __init__(self, enabled=True, animate=True):
        self.animate = animate
        self._devices = []          # (handle, dos name, unit id)
        self._queue = queue.Queue()
        self._mode = "normal"
        if enabled:
            self._open()
        if self._devices:
            threading.Thread(target=self._run, name="lights", daemon=True).start()

    @property
    def available(self):
        return bool(self._devices)

    # ── Device access ────────────────────────────────────────────────────────

    @staticmethod
    def _undefine(name, target):
        # Raw path + remove + exact match: fails once our definition is gone,
        # unlike a plain remove, which keeps "succeeding" forever.
        for _ in range(8):
            if not _k32.DefineDosDeviceW(1 | 2 | 4, name, target):
                break

    def _open(self):
        for n in range(8):
            name, target = "GemKbd%d" % n, r"\Device\KeyboardClass%d" % n
            self._undefine(name, target)            # leftovers from a crash
            if not _k32.DefineDosDeviceW(1, name, target):
                continue
            h = _k32.CreateFileW(r"\\.\%s" % name, 0, 3, None, 3, 0, None)
            if not h or h == _INVALID:
                self._undefine(name, target)
                continue
            out, ret = _Indicators(), wt.DWORD()
            if _k32.DeviceIoControl(h, IOCTL_KEYBOARD_QUERY_INDICATORS, None, 0, ctypes.byref(out),
                                    ctypes.sizeof(out), ctypes.byref(ret), None):
                self._devices.append((h, name, out.UnitId))
            else:
                _k32.CloseHandle(h)
                self._undefine(name, target)
        log.info("Keyboard lights: %d device(s)", len(self._devices))

    def _set(self, flags):
        ret = wt.DWORD()
        for h, _, unit in self._devices:
            p = _Indicators(unit, flags)
            _k32.DeviceIoControl(h, IOCTL_KEYBOARD_SET_INDICATORS, ctypes.byref(p), ctypes.sizeof(p),
                                 None, 0, ctypes.byref(ret), None)

    @staticmethod
    def _system_flags():
        flags = 0
        if toggle_state(VK["num"]):
            flags |= NUM
        if toggle_state(VK["caps"]):
            flags |= CAPS
        if toggle_state(VK["scroll"]):
            flags |= SCROLL
        return flags

    # ── Public API ───────────────────────────────────────────────────────────

    def show(self, mode):
        """mode: "talk" (all on), "mute" (all off) or "normal" (real lock states)."""
        if self._devices:
            self._queue.put(("show", mode))

    def flash(self, pattern):
        """pattern: "push_to_talk", "always_listening", "alert" or "ack"."""
        if self._devices:
            self._queue.put(("flash", pattern))

    def close(self):
        if not self._devices:
            return
        try:
            self._set(self._system_flags())
        finally:
            for h, name, _ in self._devices:
                _k32.CloseHandle(h)
                self._undefine(name, r"\Device\KeyboardClass%s" % name[len("GemKbd"):])
            self._devices = []

    # ── Animation thread ─────────────────────────────────────────────────────

    def _steps(self, frames, delay):
        """Play frames; bail out early if a new request arrives."""
        for f in frames:
            self._set(f)
            end = time.time() + delay
            while time.time() < end:
                if not self._queue.empty():
                    return False
                time.sleep(0.01)
        return True

    def _hold_flags(self):
        return {"talk": ALL, "mute": 0}.get(self._mode, self._system_flags())

    def _run(self):
        while True:
            try:
                kind, arg = self._queue.get(timeout=0.4)
            except queue.Empty:
                # Re-assert held states in case Windows rewrote the lights.
                if self._mode in ("talk", "mute"):
                    self._set(self._hold_flags())
                continue
            try:
                if kind == "show":
                    previous, self._mode = self._mode, arg
                    if arg == "talk":
                        if self.animate and previous != "talk":
                            self._steps(_SWEEP, 0.045)
                        self._set(ALL)
                    elif arg == "mute":
                        self._set(0)
                    else:
                        if self.animate and previous == "talk":
                            self._steps(list(reversed(_SWEEP[:-1])) + [0], 0.04)
                        self._set(self._system_flags())
                elif kind == "flash":
                    if arg == "push_to_talk":
                        frames = [ALL, 0, ALL, 0]
                        delay = 0.12
                    elif arg == "always_listening":
                        frames = [NUM, CAPS, SCROLL, CAPS, NUM, ALL, 0]
                        delay = 0.07
                    elif arg == "ack":
                        frames = [ALL, 0]
                        delay = 0.08
                    else:   # alert
                        frames = [ALL, 0] * 4
                        delay = 0.18
                    self._steps(frames, delay)
                    self._set(self._hold_flags())
            except Exception:
                log.exception("Light animation failed")
