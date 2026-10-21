"""External monitor brightness over DDC/CI (VCP code 0x10), the same channel as the monitor's own buttons.

Most monitors support it; some ship with it switched off (look for "DDC/CI" in the monitor's menu).
"""
import ctypes
import ctypes.wintypes as wt
import logging
import threading

log = logging.getLogger("gem.monitors")

VCP_BRIGHTNESS = 0x10

user32 = ctypes.windll.user32
dxva2 = ctypes.windll.dxva2


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [("handle", wt.HANDLE), ("description", wt.WCHAR * 128)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wt.HMONITOR, ctypes.POINTER(wt.DWORD)]
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [wt.HMONITOR, wt.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.DestroyPhysicalMonitors.argtypes = [wt.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [wt.HANDLE, wt.BYTE, ctypes.c_void_p,
                                                  ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD)]
dxva2.SetVCPFeature.argtypes = [wt.HANDLE, wt.BYTE, wt.DWORD]

_lock = threading.Lock()                       # DDC/CI is a slow serial bus; one conversation at a time


class _Physical:
    """All physical monitors, released again on exit."""

    def __enter__(self):
        self.groups = []
        hmons = []

        def cb(hmon, hdc, rect, data):
            hmons.append(hmon)
            return True

        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
        for hmon in hmons:
            n = wt.DWORD()
            if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, ctypes.byref(n)) or not n.value:
                continue
            arr = (PHYSICAL_MONITOR * n.value)()
            if dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, n.value, arr):
                self.groups.append((n.value, arr))
        return [m for _, arr in self.groups for m in arr]

    def __exit__(self, *exc):
        for n, arr in self.groups:
            dxva2.DestroyPhysicalMonitors(n, arr)


def _get(handle):
    cur, mx = wt.DWORD(), wt.DWORD()
    if dxva2.GetVCPFeatureAndVCPFeatureReply(handle, VCP_BRIGHTNESS, None, ctypes.byref(cur), ctypes.byref(mx)) \
            and mx.value:
        return cur.value, mx.value
    return None


def brightness():
    """[(monitor name, brightness 0-100)] for monitors that answer over DDC/CI."""
    out = []
    with _lock, _Physical() as mons:
        for m in mons:
            got = _get(m.handle)
            if got:
                out.append((m.description or "Monitor", round(got[0] * 100 / got[1])))
    return out


def set_brightness(level=None, change=None):
    """Set (0-100) or nudge (+/-) every DDC/CI monitor. Returns [(name, new level)] for the ones that took it."""
    done = []
    with _lock, _Physical() as mons:
        for m in mons:
            got = _get(m.handle)
            if not got:
                continue
            cur, mx = got
            pct = cur * 100.0 / mx
            target = level if level is not None else pct + (change or 0)
            target = max(0, min(100, int(round(target))))
            if dxva2.SetVCPFeature(m.handle, VCP_BRIGHTNESS, int(round(target * mx / 100.0))):
                done.append((m.description or "Monitor", target))
            else:
                log.warning("Monitor %r didn't accept brightness %d", m.description, target)
    return done
