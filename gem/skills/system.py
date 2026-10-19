"""PC control: volume, media, windows, power, screenshots and system info."""
import datetime
import logging
import os
import socket
import subprocess
import time

import psutil
import requests

from ..actions import ActionError, action
from ..cards import card
from ..parse import duration_phrase
from ..runtime import svc
from ..winapi import SW_MAXIMIZE, SW_MINIMIZE, foreground_window, known_folder, lock_workstation, press, \
    show_window, window_rect_physical

log = logging.getLogger("gem.system")


# ── Clock ────────────────────────────────────────────────────────────────────

@action("clock", "Current time or date.", "what: time|date", ai=False)
def clock(what="time"):
    now = datetime.datetime.now()
    t, d = now.strftime("%I:%M %p").lstrip("0"), now.strftime("%A, %B %d, %Y").replace(" 0", " ")
    return card("clock", "It's %s." % (d if what == "date" else t), time=t, date=d)


# ── Volume ───────────────────────────────────────────────────────────────────

def _endpoint():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def _master():
    return int(round(_endpoint().GetMasterVolumeLevelScalar() * 100))


def _sessions(app):
    from pycaw.pycaw import AudioUtilities
    from .apps import _process_names
    wanted = set(_process_names(app))
    return [s for s in AudioUtilities.GetAllSessions() if s.Process and s.Process.name().lower() in wanted]


@action("volume", "System or app volume: level 0-100, change (e.g. -15 to lower), or mute.", "level?: number, change?: number, mute?: bool, app?: str")
def volume(level=None, change=None, mute=None, app=None):
    if app:
        return _app_volume(app, level, change, mute)
    ep = _endpoint()
    if mute is not None:
        ep.SetMute(1 if mute else 0, None)
        return card("volume", "Muted." if mute else "Unmuted.", level=_master(), muted=bool(mute))
    if level is None and change is None:
        muted = bool(ep.GetMute())
        return card("volume", "Volume is at %d percent%s." % (_master(), ", muted" if muted else ""),
                    level=_master(), muted=muted)
    new = int(level) if level is not None else _master() + int(change)
    new = max(0, min(100, new))
    ep.SetMasterVolumeLevelScalar(new / 100.0, None)
    if ep.GetMute() and new > 0:
        ep.SetMute(0, None)
    return card("volume", "Volume %d." % new, level=new, muted=False)


def _app_volume(app, level, change, mute):
    sessions = _sessions(app)
    if not sessions:
        return "%s isn't playing any sound." % app.capitalize()
    for s in sessions:
        v = s.SimpleAudioVolume
        if mute is not None:
            v.SetMute(1 if mute else 0, None)
        elif level is not None or change is not None:
            cur = v.GetMasterVolume() * 100
            new = int(level) if level is not None else cur + int(change)
            v.SetMasterVolume(max(0, min(100, new)) / 100.0, None)
    cur = int(round(sessions[0].SimpleAudioVolume.GetMasterVolume() * 100))
    if mute is not None:
        return card("volume", "%s %s." % (app.capitalize(), "muted" if mute else "unmuted"), level=cur,
                    muted=bool(mute), app=app)
    return card("volume", "%s volume %d." % (app.capitalize(), cur), level=cur, muted=False, app=app)


# ── Media ────────────────────────────────────────────────────────────────────

@action("media", "Media keys.", "command: play_pause|next|previous")
def media(command="play_pause"):
    keys = {"play_pause": "play_pause", "play": "play_pause", "pause": "play_pause", "resume": "play_pause",
            "next": "next", "skip": "next", "previous": "prev", "prev": "prev", "back": "prev", "stop": "stop"}
    key = keys.get(command)
    if not key:
        raise ActionError("I can play, pause, skip or go back.")
    press(key)
    return None


@action("now_playing", "Current Spotify song.")
def now_playing():
    from ..winapi import top_windows
    for _, title, proc in top_windows():
        if proc == "spotify.exe":
            if title.lower().startswith("spotify"):
                return "Spotify is paused."
            if " - " in title:
                artist, song = title.split(" - ", 1)
                return card("music", "Playing %s by %s." % (song, artist), title=song, artist=artist, playing=True)
            return card("music", title, title=title, artist="Spotify", playing=True)
    return "Spotify isn't playing anything."


# ── Windows ──────────────────────────────────────────────────────────────────

@action("window", "Arrange windows.", "command: show_desktop|minimize|maximize|snap_left|snap_right|task_view")
def window(command="show_desktop"):
    hwnd = foreground_window()
    if command == "show_desktop":
        press("win", "d")
    elif command == "minimize":
        show_window(hwnd, SW_MINIMIZE)
    elif command == "maximize":
        show_window(hwnd, SW_MAXIMIZE)
    elif command == "snap_left":
        press("win", "left")
    elif command == "snap_right":
        press("win", "right")
    elif command == "switch_desktop_left":
        press("ctrl", "win", "left")
    elif command == "switch_desktop_right":
        press("ctrl", "win", "right")
    elif command == "task_view":
        press("win", "tab")
    else:
        raise ActionError("I can't do that with windows.")
    return None


# ── Power ────────────────────────────────────────────────────────────────────

POWER_WORDS = {"shutdown": "shut down", "restart": "restart", "sleep": "put the PC to sleep",
               "sign_out": "sign you out", "hibernate": "hibernate"}


@action("power", "Lock, sleep, restart, shut down or sign out (asks to confirm).", "command: lock|sleep|restart|shutdown|sign_out|cancel_shutdown")
def power(command="lock"):
    if command == "lock":
        lock_workstation()
        return None
    if command == "cancel_shutdown":
        subprocess.run(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)
        return "Cancelled."
    if command not in POWER_WORDS:
        raise ActionError("I can lock, sleep, restart, shut down or sign out.")
    svc.assistant.confirm("Should I %s? Say yes to confirm." % POWER_WORDS[command],
                          lambda: _do_power(command))
    return None


def _do_power(command):
    flags = subprocess.CREATE_NO_WINDOW
    if command == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "10"], creationflags=flags)
        return "Shutting down in 10 seconds. Say cancel shutdown to stop it."
    if command == "restart":
        subprocess.run(["shutdown", "/r", "/t", "10"], creationflags=flags)
        return "Restarting in 10 seconds. Say cancel shutdown to stop it."
    if command == "sign_out":
        subprocess.run(["shutdown", "/l"], creationflags=flags)
        return None
    if command in ("sleep", "hibernate"):
        import ctypes
        ctypes.windll.powrprof.SetSuspendState(command == "hibernate", True, False)
        return None
    return None


# ── Info ─────────────────────────────────────────────────────────────────────

@action("system_info", "PC status.", "what: overview|cpu|ram|disk|battery|uptime|top_processes|ip|network")
def system_info(what="overview"):
    gb = 1024 ** 3
    if what in ("cpu", "ram", "overview"):
        cpu = psutil.cpu_percent(interval=0.6)
        m = psutil.virtual_memory()
        c = psutil.disk_usage("C:\\")
        b = psutil.sensors_battery()
        stats = dict(cpu=cpu, ram=m.percent, disk=c.percent, battery=b.percent if b else None, highlight=what)
        if what == "cpu":
            return card("system", "CPU is at %d percent." % cpu, **stats)
        if what == "ram":
            return card("system", "Using %.1f of %.0f gigabytes of RAM, %d percent." % (m.used / gb, m.total / gb,
                                                                                    m.percent), **stats)
        return card("system", "CPU %d percent, RAM %d percent used, %.0f gigabytes free on C." % (
            cpu, m.percent, c.free / gb), **stats)
    if what == "disk":
        parts = []
        for p in psutil.disk_partitions():
            if "fixed" not in p.opts and "rw" not in p.opts:
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
            except OSError:
                continue
            parts.append("%s has %.0f gigabytes free of %.0f" % (p.mountpoint[0], u.free / gb, u.total / gb))
        return (". ".join(parts) + ".") if parts else "I couldn't read your drives."
    if what == "battery":
        b = psutil.sensors_battery()
        if not b:
            return "This PC doesn't have a battery."
        state = "charging" if b.power_plugged else "on battery"
        left = "" if b.power_plugged or b.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) \
            else ", about %s left" % duration_phrase(b.secsleft - b.secsleft % 60)
        return "Battery is at %d percent, %s%s." % (b.percent, state, left)
    if what == "uptime":
        up = time.time() - psutil.boot_time()
        return "Your PC has been on for %s." % duration_phrase(up - up % 60)
    if what == "top_processes":
        procs = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                procs.append((p.info["memory_info"].rss, p.info["name"]))
            except Exception:
                pass
        merged = {}
        for rss, name in procs:
            merged[name] = merged.get(name, 0) + rss
        top = sorted(merged.items(), key=lambda x: -x[1])[:3]
        return "Using the most memory: " + ", ".join("%s with %.1f gigabytes" % (n.replace(".exe", ""), r / gb)
                                                    for n, r in top) + "."
    if what == "ip":
        local = socket.gethostbyname(socket.gethostname())
        try:
            public = requests.get("https://api.ipify.org", timeout=4).text
        except Exception:
            public = "unavailable"
        return "Your local IP is %s and your public IP is %s." % (local, public)
    if what == "network":
        return ping()
    return system_info("overview")


@action("ping", "Test the internet connection speed.", ai=False)
def ping():
    times = []
    for _ in range(3):
        try:
            start = time.time()
            requests.head("https://www.google.com", timeout=4)
            times.append((time.time() - start) * 1000)
        except Exception:
            pass
    if not times:
        return "I can't reach the internet."
    return "Internet is working. Response time is about %d milliseconds." % min(times)


# ── Screenshots ──────────────────────────────────────────────────────────────

@action("screenshot", "Screenshot to Desktop and clipboard.", "region?: screen|window|snip")
def screenshot(region="screen"):
    if region == "snip":
        press("win", "shift", "s")
        return None
    from io import BytesIO
    import win32clipboard
    from PIL import ImageGrab
    if svc.overlay:
        svc.overlay.suppress(1.0)            # keep Gem out of the picture
        time.sleep(0.3)
    if region == "window":
        img = ImageGrab.grab(bbox=window_rect_physical(foreground_window()), all_screens=True)
    else:
        img = ImageGrab.grab(all_screens=True)
    folder = svc.config.get("screenshot_dir") or known_folder("desktop")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "screenshot_%s.png" % datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    img.save(path)
    out = BytesIO()
    img.convert("RGB").save(out, "BMP")
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, out.getvalue()[14:])
    finally:
        win32clipboard.CloseClipboard()
    if svc.lights:
        svc.lights.flash("ack")
    if svc.sounds:
        svc.sounds.play("ack")
    return card("image", "Screenshot saved and copied.", path=path)


# ── Display ──────────────────────────────────────────────────────────────────

@action("dark_mode", "Windows dark mode.", "on: bool")
def dark_mode(on=True):
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", 0, winreg.KEY_SET_VALUE)
    value = 0 if on else 1
    winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
    winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
    winreg.CloseKey(key)
    return "Dark mode on." if on else "Light mode on."


@action("brightness", "Screen brightness (laptops).", "level: number")
def brightness(level=50):
    level = max(0, min(100, int(level)))
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
                        ".WmiSetBrightness(1,%d)" % level],
                       capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode != 0 or "Exception" in (r.stderr or ""):
        return "I can't change the brightness on this screen."
    return "Brightness %d." % level
