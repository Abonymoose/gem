"""A few surprises. Deliberately left out of the help text and the README."""
import collections
import datetime
import json
import logging
import os
import random

from .actions import action
from .config import DATA_DIR, runtime
from .runtime import say, svc

log = logging.getLogger("gem.eggs")

MILESTONES = (100, 250, 500, 1000, 2500, 5000, 10000)
NICE = {"set_timer": "timers", "weather": "the weather", "media": "music controls", "open_app": "opening apps",
        "volume": "volume", "clock": "the time", "web_answer": "questions", "set_reminder": "reminders",
        "set_alarm": "alarms", "todo_add": "your to-do list", "youtube": "YouTube", "calculate": "maths",
        "convert": "conversions", "explain_screen": "explaining your screen", "screenshot": "screenshots",
        "clip_that": "clips", "picks": "picks", "countdown": "countdowns", "time_in": "world times"}


def _fx(kind, seconds):
    if svc.overlay and hasattr(svc.overlay, "fx"):
        svc.overlay.fx(kind, seconds)


def after_reply(source):
    """Runs after every answer to a real request."""
    if source not in ("ptt", "typed", "open"):
        return
    try:
        _birthday()
        _milestone()
    except Exception:
        log.debug("Egg check failed", exc_info=True)


def _birthday():
    from .skills.world import store
    b = (store.data.get("dates") or {}).get("birthday")
    today = datetime.date.today()
    if not b or (b.get("month"), b.get("day")) != (today.month, today.day):
        return
    if runtime.data.get("egg_birthday") == today.isoformat():
        return
    with runtime as d:
        d["egg_birthday"] = today.isoformat()
    name = svc.config.get("user_name") or ""
    _fx("confetti", 8)
    say(random.choice(["Oh, and happy birthday%s! Hope it's a great one.",
                       "Wait, it's your birthday! Happy birthday%s."]) % (", " + name if name else ""),
        card={"kind": "alert", "title": "Happy birthday%s!" % (", " + name if name else ""),
              "message": "From Gem, with confetti."})


def _milestone():
    with runtime as d:
        if "egg_count" not in d:                                   # start from what's already in the history
            d["egg_count"] = _history_count()
        d["egg_count"] += 1
        n = d["egg_count"]
    if n not in MILESTONES:
        return
    top, since = _stats()
    fav = ", then ".join(NICE.get(a, a.replace("_", " ")) for a, _ in top[:3])
    text = "By the way, that was request number %d. %s" % (n, ("You use me most for %s." % fav) if fav else "")
    _fx("confetti", 5)
    rows = [{"icon": "dot", "text": "%s · %d time%s" % (NICE.get(a, a.replace("_", " ")).capitalize(), c,
                                                         "" if c == 1 else "s")} for a, c in top[:4]]
    if since:
        rows.append({"icon": "dot", "text": "Together since %s" % since})
    say(text, card={"kind": "briefing", "greeting": "%d requests" % n, "rows": rows})


def _history_lines():
    path = os.path.join(DATA_DIR, "history.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            return f.readlines()
    except OSError:
        return []


def _history_count():
    return len(_history_lines())


def _stats():
    counts, first = collections.Counter(), None
    for line in _history_lines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        first = first or e.get("t")
        for a in e.get("actions") or []:
            if a not in ("snooze", "resume", "stop", "repeat"):
                counts[a] += 1
    since = datetime.datetime.fromtimestamp(first).strftime("%B %Y") if first else None
    return counts.most_common(4), since


@action("barrel_roll", "", ai=False)
def barrel_roll():
    _fx("roll", 1.3)
    return random.choice(["Wheee.", "Done. Slightly dizzy.", "Barrel roll complete.", "Again? No. Okay, maybe."])


@action("general_kenobi", "", ai=False)
def general_kenobi():
    _fx("roll", 0.9)
    return "General Kenobi."
