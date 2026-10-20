"""Heads-ups: Gem tells you before it matters. Rain soon, a download finished, the PC struggling, battery low,
and reminders tied to opening an app. Quiet toasts, held back during calls and games.
"""
import logging
import os
import threading
import time

import psutil
import requests

from .config import JsonStore
from .runtime import caption, notify, svc

log = logging.getLogger("gem.headsup")

app_reminders = JsonStore("app_reminders.json", {"items": []})

_last_said = {}
_pending = []                   # (key, text, created) held back during calls and games
PARTIAL = (".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload", ".!ut", ".aria2")
RAIN_CODES = set(range(51, 68)) | set(range(80, 83)) | {95, 96, 99}


def cfg():
    return svc.config.get("heads_up") or {}


def _busy():
    from . import hype
    st = svc.state
    return st.in_call or st.gaming or st.snoozed or hype.state["in_game"]


def tell(key, text, cooldown):
    """Show a heads-up unless the same one was shown recently; hold it while you're busy."""
    now = time.time()
    if now - _last_said.get(key, 0) < cooldown:
        return
    _last_said[key] = now
    if _busy():
        _pending.append((key, text, now))
        return
    _show(text)


def _show(text):
    log.info("Heads-up: %s", text)
    if len(text) <= 52:
        caption(text, seconds=5)
    else:
        caption(text, seconds=8, card={"kind": "alert", "title": "Heads-up", "message": text})


def _flush_pending():
    if _pending and not _busy():
        fresh = [(k, t) for k, t, c in _pending if time.time() - c < 30 * 60]
        _pending.clear()
        for _, text in fresh[-2:]:
            _show(text)
            time.sleep(6)


# ── Checks ───────────────────────────────────────────────────────────────────

def _rain():
    city = (svc.config.get("home_city") or "").strip()
    if not city:
        return
    from .skills.web import _geocode
    geo = _geocode(city)
    if not geo:
        return
    lat, lon, _ = geo
    d = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1, "current": "weather_code",
        "minutely_15": "precipitation", "forecast_minutely_15": 8}, timeout=8).json()
    if d.get("current", {}).get("weather_code") in RAIN_CODES:
        return                                          # already raining; no news there
    times = d.get("minutely_15", {}).get("time") or []
    rain = d.get("minutely_15", {}).get("precipitation") or []
    import datetime
    now = datetime.datetime.now()
    for t, mm in zip(times, rain):
        when = datetime.datetime.fromisoformat(t)
        if mm and mm >= 0.2 and when > now:
            mins = max(5, int((when - now).total_seconds() // 60 // 5 * 5))
            tell("rain", "Rain likely in about %d minutes" % mins, 3 * 3600)
            return


_seen_downloads = {}


def _downloads():
    from .winapi import known_folder
    folder = known_folder("downloads")
    now = time.time()
    try:
        entries = [e for e in os.scandir(folder) if e.is_file()]
    except OSError:
        return
    names = {e.name for e in entries}
    for e in entries:
        st = e.stat()
        if e.name.lower().endswith(PARTIAL) or st.st_size < 2_000_000 or now - st.st_mtime > 600:
            continue
        if any(n.startswith(e.name) and n.lower().endswith(PARTIAL) for n in names):
            continue
        prev = _seen_downloads.get(e.name)
        _seen_downloads[e.name] = st.st_size
        if prev is not None and prev == st.st_size and not _seen_downloads.get(e.name + "#told"):
            _seen_downloads[e.name + "#told"] = True
            nice = e.name if len(e.name) <= 36 else e.name[:33] + "..."
            tell("dl:" + e.name, "Download finished: %s" % nice, 3600)


_hot = {"cpu": 0, "ram": 0}


def _pc():
    from . import hype
    cpu = psutil.cpu_percent(interval=1.0)
    ram = psutil.virtual_memory().percent
    _hot["cpu"] = _hot["cpu"] + 1 if cpu > 90 else 0
    _hot["ram"] = _hot["ram"] + 1 if ram > 92 else 0
    if (_hot["cpu"] >= 3 or _hot["ram"] >= 2) and not hype.state["in_game"]:
        top = _top_process("cpu" if _hot["cpu"] >= 3 else "ram")
        if top:
            what = "your CPU" if _hot["cpu"] >= 3 else "most of your memory"
            tell("pc:" + top, "%s is using %s" % (top, what), 30 * 60)
    try:
        free = psutil.disk_usage(os.environ.get("SYSTEMDRIVE", "C:") + "\\").free
        if free < 5e9:
            tell("disk", "Your C drive is almost full: %.1f GB left" % (free / 1e9), 24 * 3600)
    except Exception:
        pass
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bat and not bat.power_plugged and bat.percent <= 15:
        tell("battery%d" % (5 if bat.percent <= 5 else 15), "Battery at %d%%, plug in soon" % bat.percent, 30 * 60)


def _top_process(kind):
    from .skills.insights import APP_NAMES
    best, val = None, 0.0
    for p in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
        try:
            v = p.info["cpu_percent"] if kind == "cpu" else p.info["memory_info"].rss
        except Exception:
            continue
        name = (p.info["name"] or "").lower()
        if v and v > val and name not in ("system idle process", "system", "gem.exe", "memory compression"):
            best, val = name, v
    return APP_NAMES.get(best) or (best or "").replace(".exe", "").title() if best else None


# ── App reminders: "remind me to X when I open Discord" ──────────────────────

def _app_matches(app, proc):
    from .skills.insights import APP_NAMES
    a = app.lower().replace(" ", "")
    name = (APP_NAMES.get(proc) or proc.replace(".exe", "")).lower().replace(" ", "")
    return a == name or a in name or a in proc.replace(" ", "")


def _watch_apps():
    from .winapi import foreground_window, window_process_name
    last = ""
    while True:
        time.sleep(2)
        try:
            items = app_reminders.data.get("items") or []
            if not items:
                continue
            proc = window_process_name(foreground_window())
            if not proc or proc == last:
                continue
            last = proc
            due = [i for i in items if _app_matches(i["app"], proc)]
            if not due:
                continue
            with app_reminders as data:
                data["items"] = [i for i in data["items"] if i not in due]
            for i in due:
                notify("Reminder", "You asked me to remind you: %s." % i["message"].rstrip("."), sound="soft")
        except Exception:
            log.debug("App reminder check failed", exc_info=True)


def _loop():
    n = 0
    while True:
        time.sleep(60)
        n += 1
        c = cfg()
        for name, fn, every in (("rain", _rain, 20), ("downloads", _downloads, 1), ("pc", _pc, 1)):
            if c.get(name, True) and n % every == 0:
                try:
                    fn()
                except Exception as e:
                    log.debug("Heads-up %s failed: %s", name, e)
        _flush_pending()


def start():
    threading.Thread(target=_loop, name="heads-up", daemon=True).start()
    threading.Thread(target=_watch_apps, name="app-reminders", daemon=True).start()
