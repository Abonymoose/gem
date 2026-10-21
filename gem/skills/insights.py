"""Screen time (which apps and sites you use, tracked locally) and a recap of your day."""
import datetime
import json
import logging
import os
import re
import threading
import time

from .. import winapi
from ..actions import action
from ..cards import card
from ..config import DATA_DIR, JsonStore
from ..parse import duration_phrase
from ..runtime import svc
from . import timeline

log = logging.getLogger("gem.insights")

usage = JsonStore("usage.json", {"days": {}})

APP_NAMES = {
    "brave.exe": "Brave", "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "discord.exe": "Discord", "spotify.exe": "Spotify", "code.exe": "VS Code", "explorer.exe": "File Explorer",
    "steam.exe": "Steam", "steamwebhelper.exe": "Steam", "fortniteclient-win64-shipping.exe": "Fortnite",
    "robloxplayerbeta.exe": "Roblox", "javaw.exe": "Minecraft", "minecraft.windows.exe": "Minecraft",
    "rocketleague.exe": "Rocket League", "lunar client.exe": "Lunar Client", "winword.exe": "Word",
    "excel.exe": "Excel", "powerpnt.exe": "PowerPoint", "notepad.exe": "Notepad", "windowsterminal.exe": "Terminal",
    "obs64.exe": "OBS", "whatsapp.exe": "WhatsApp", "ms-teams.exe": "Teams", "zoom.exe": "Zoom",
    "epicgameslauncher.exe": "Epic Games", "claude.exe": "Claude", "aoe2de_s.exe": "Age of Empires II",
    "geometrydash.exe": "Geometry Dash",
}
BROWSERS = {"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe"}
SITES = ["YouTube", "Netflix", "Twitch", "Gmail", "Google Docs", "Google Classroom", "Classroom", "Google Chat",
         "Reddit", "Instagram", "ChatGPT", "Claude", "GitHub", "Wikipedia", "X", "Twitter", "WhatsApp", "Discord",
         "Spotify", "Google Drive", "Google Slides", "Google Sheets", "Amazon", "TikTok"]
SKIP = {"lockapp.exe", "searchhost.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe", "", "gem.exe",
        "python.exe", "pythonw.exe", "pythonw3.12.exe", "python3.12.exe"}

_pending = {}
_lock = threading.Lock()


def _label(hwnd):
    proc = winapi.window_process_name(hwnd)
    if proc in SKIP:
        return None
    if proc in BROWSERS:
        title = winapi.window_title(hwnd)
        for site in SITES:
            if re.search(r"(?:^|[-|·] )%s(?: |$|[-|·])" % re.escape(site), title):
                return "Classroom" if site == "Google Classroom" else site
    if proc in APP_NAMES:
        return APP_NAMES[proc]
    # "VALORANT-Win64-Shipping.exe" -> "Valorant"
    base = re.sub(r"(?i)[-_. ]*(?:win64|win32|x64|x86|shipping|dx11|dx12)\b", "", proc[:-4] if proc.endswith(".exe")
                  else proc)
    return (base or proc).replace("_", " ").strip().title()


def start_tracker(interval=5):
    def run():
        last_flush = time.time()
        while True:
            time.sleep(interval)
            try:
                if winapi.idle_seconds() < 120:
                    hwnd = winapi.foreground_window()
                    name = _label(hwnd) if hwnd else None
                    if name:
                        with _lock:
                            _pending[name] = _pending.get(name, 0) + interval
                        timeline.sample(name, winapi.window_title(hwnd), time.time(), interval)
                if time.time() - last_flush > 60:
                    flush()
                    last_flush = time.time()
            except Exception:
                log.debug("Screen time sample failed", exc_info=True)

    threading.Thread(target=run, name="screen-time", daemon=True).start()


def flush():
    try:
        timeline.flush()
    except Exception:
        log.debug("Timeline save failed", exc_info=True)
    with _lock:
        pending = dict(_pending)
        _pending.clear()
    if not pending:
        return
    day = datetime.date.today().isoformat()
    with usage as data:
        d = data["days"].setdefault(day, {})
        for k, v in pending.items():
            d[k] = d.get(k, 0) + v
        for old in sorted(data["days"])[:-60]:       # keep two months
            data["days"].pop(old)


def _totals(days):
    flush()
    today = datetime.date.today()
    out = {}
    for i in range(days):
        d = usage.data.get("days", {}).get((today - datetime.timedelta(days=i)).isoformat(), {})
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out


def _phrase(secs):
    secs = int(secs)
    if secs < 60:
        return "under a minute"
    return duration_phrase(secs - secs % 60)


@action("screen_time", "Screen time: how long the user spent on apps and sites, today or this week, or on one app.",
        "app?: str, period?: today|week")
def screen_time(app="", period="today"):
    days = 7 if period == "week" else 1
    totals = _totals(days)
    when = "this week" if days == 7 else "today"
    if not totals:
        return "I don't have any screen time for %s yet." % when
    if app:
        a = app.lower().strip()
        hit = next((k for k in totals if k.lower() == a), None) or next((k for k in totals if a in k.lower()), None)
        if not hit:
            return "You haven't used %s %s." % (app, when)
        return "You've spent %s on %s %s." % (_phrase(totals[hit]), hit, when)
    total = sum(totals.values())
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
    rows = [{"name": k, "secs": v} for k, v in top]
    text = "%s of screen time %s. Most of it on %s." % (_phrase(total).capitalize(), when,
                                                       ", ".join("%s, %s" % (k, _phrase(v)) for k, v in top[:3]))
    return card("usage", text, total=_phrase(total), period=when, rows=rows)


@action("day_recap", "Summarize what the user did today: commands, to-dos, habits, focus and screen time.")
def day_recap():
    from . import habits
    from .productivity import todos
    today = datetime.date.today()
    lines = []
    hist = os.path.join(DATA_DIR, "history.jsonl")
    asked = []
    if os.path.exists(hist):
        with open(hist, "r", encoding="utf-8") as f:
            for line in f.readlines()[-400:]:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if datetime.date.fromtimestamp(e.get("t", 0)) == today and e.get("you"):
                    asked.append(e["you"])
    if asked:
        lines.append("Things they asked Gem today: " + "; ".join(asked[-25:]))
    done = [i["text"] for i in todos.data.get("items", [])
            if i.get("done") and i.get("done_at") and datetime.date.fromtimestamp(i["done_at"]) == today]
    if done:
        lines.append("To-dos finished: " + ", ".join(done))
    logs = habits.store.data.get("log", {})
    hab = ["%s %d" % (k, v.get(today.isoformat(), 0)) for k, v in logs.items() if v.get(today.isoformat())]
    if hab:
        lines.append("Habits logged: " + ", ".join(hab))
    totals = _totals(1)
    if totals:
        top = sorted(totals.items(), key=lambda kv: -kv[1])[:5]
        lines.append("Screen time: " + ", ".join("%s %d min" % (k, v // 60) for k, v in top))
    if not lines:
        return "There isn't much to recap yet today."
    name = svc.config.get("user_name") or "the user"
    summary = svc.brain.complete(
        "Write a two to three sentence spoken recap of %s's day so far from these notes, addressed to them as "
        "'you'. Plain, direct sentences like a good assistant would say. No lists, no dashes, no judgement, no "
        "flowery words, highlights only." % name, "\n".join(lines), max_tokens=200)
    rows = []
    if done:
        rows.append({"icon": "todo", "text": "Finished: " + ", ".join(done[:4])})
    if hab:
        rows.append({"icon": "bell", "text": "Habits: " + ", ".join(hab)})
    if totals:
        top = sorted(totals.items(), key=lambda kv: -kv[1])[:3]
        rows.append({"icon": "class", "text": "Screen time: " + ", ".join("%s %s" % (k, _phrase(v)) for k, v in top)})
    return card("briefing", summary, greeting="Your day so far", rows=rows or [{"icon": "todo", "text": summary}])
