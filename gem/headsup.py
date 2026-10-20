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


AWAY_AFTER_S = 10 * 60
away = {"on": False, "since": 0.0, "missed": []}


def _idle():
    from .winapi import idle_seconds
    try:
        return idle_seconds()
    except Exception:
        return 0.0


def note_missed(title, message):
    """Alerts that happen while nobody's at the PC go into a 'while you were away' summary."""
    if away["on"]:
        away["missed"].append((time.time(), title, message))
        del away["missed"][:-12]


def _watching():
    """Not touching the mouse because you're watching something isn't being away."""
    from .winapi import foreground_is_fullscreen
    try:
        from .skills.power_auto import _active_media
        return foreground_is_fullscreen() or _active_media()
    except Exception:
        return True


def _check_presence():
    idle = _idle()
    if idle > AWAY_AFTER_S and not away["on"]:
        if _watching():
            return
        away.update(on=True, since=time.time() - idle)
    elif away["on"] and idle < 5:
        mins = int((time.time() - away["since"]) // 60)
        missed = away["missed"]
        away.update(on=False, missed=[])
        if missed and not svc.state.in_call:
            rows = [{"icon": "bell", "text": "%s · %s" % (time.strftime("%I:%M %p", time.localtime(t)).lstrip("0"),
                                                          m if t_ in ("Reminder", "Heads-up") else "%s: %s" % (t_, m))}
                    for t, t_, m in missed[-5:]]
            first = missed[0][2].rstrip(".")
            say_text = ("Welcome back. While you were away: %s%s." % (first[:80], " and %d more" % (len(missed) - 1)
                                                                     if len(missed) > 1 else ""))
            from .runtime import say
            say(say_text, card={"kind": "briefing", "greeting": "While you were away (%d min)" % mins, "rows": rows})


def tell(key, text, cooldown):
    """Show a heads-up unless the same one was shown recently; hold it while you're busy or away."""
    now = time.time()
    if now - _last_said.get(key, 0) < cooldown:
        return
    _last_said[key] = now
    if away["on"]:
        away["missed"].append((now, "Heads-up", text))
        return
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


def _date_phrase(key, when):
    """'aarav's birthday' -> "Aarav's birthday is tomorrow"; 'exam' -> 'Your exam is tomorrow'."""
    if "'s " in key:
        return "%s is %s" % (key[:1].upper() + key[1:], when)
    return "Your %s is %s" % (key, when)


def _dates():
    import datetime
    from .skills.world import store
    now = datetime.datetime.now()
    today = now.date()
    for key, d in (store.data.get("dates") or {}).items():
        if key in ("birthday", "my birthday"):
            continue                                    # your own birthday has its own surprise
        try:
            day = datetime.date(today.year, int(d["month"]), int(d["day"]))
        except (KeyError, ValueError, TypeError):
            continue
        if day == today and now.hour >= 8:
            tell("date:%s:%s" % (key, today), _date_phrase(key, "today"), 24 * 3600)
        elif day == today + datetime.timedelta(days=1) and now.hour >= 17:
            tell("date:%s:%s" % (key, day), _date_phrase(key, "tomorrow"), 24 * 3600)


def _air():
    from .skills.web import _air_now
    city = (svc.config.get("home_city") or "").strip()
    if not city:
        return
    aqi, _, _ = _air_now(city)
    if aqi and aqi >= 151:
        tell("aqi", "Air quality is unhealthy now (AQI %d)" % aqi, 12 * 3600)


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


def _watch_presence():
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass
    while True:
        time.sleep(3)
        try:
            _check_presence()
        except Exception:
            log.debug("Presence check failed", exc_info=True)


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
        for name, fn, every in (("rain", _rain, 20), ("downloads", _downloads, 1), ("pc", _pc, 1),
                                ("dates", _dates, 30), ("air", _air, 60)):
            if c.get(name, True) and n % every == 0:
                try:
                    fn()
                except Exception as e:
                    log.debug("Heads-up %s failed: %s", name, e)
        _flush_pending()


def start():
    threading.Thread(target=_loop, name="heads-up", daemon=True).start()
    threading.Thread(target=_watch_apps, name="app-reminders", daemon=True).start()
    threading.Thread(target=_watch_presence, name="presence", daemon=True).start()
