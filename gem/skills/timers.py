"""Timers, alarms, reminders, the weekly class schedule and break reminders.

Everything is saved to reminders.json with absolute times, so it all survives
a restart. Alerts adapt to the situation: spoken normally, a caption, popup
and light flash during calls, snooze or gaming.
"""
import datetime
import json
import logging
import os
import re
import threading
import time
import uuid
import webbrowser

from ..actions import ActionError, action
from ..config import PROJECT_DIR, JsonStore
from ..parse import WEEKDAYS, clock_phrase, duration_phrase, normalize_time_words, parse_duration, parse_when
from ..runtime import caption, notify, svc
from ..winapi import idle_seconds

log = logging.getLogger("gem.timers")

DEFAULT_SCHEDULE = [
    {"name": "french class", "days": ["monday"], "time": "19:55",
     "message": "Time for French class.", "url": "https://meet.google.com/oot-vnfo-yhp"},
    {"name": "english class", "days": ["tuesday", "thursday"], "time": "18:55",
     "message": "Time for English class.", "url": "https://meet.google.com/tsf-ynjp-qhc?pli=1"},
    {"name": "french class", "days": ["wednesday"], "time": "18:55",
     "message": "Time for French class.", "url": "https://meet.google.com/oot-vnfo-yhp"},
]

store = JsonStore("reminders.json", {"items": [], "schedule": None})


def _migrate():
    with store as data:
        if data.get("schedule") is not None:
            return
        old = os.path.join(PROJECT_DIR, "gem_alarms.json")
        schedule = DEFAULT_SCHEDULE
        if os.path.exists(old):
            try:
                with open(old, "r", encoding="utf-8") as f:
                    schedule = json.load(f)
                log.info("Imported class schedule from %s", old)
            except Exception as e:
                log.error("Could not import %s: %s", old, e)
        data["schedule"] = schedule


def _add(kind, at, label="", message="", url=None):
    item = {"id": uuid.uuid4().hex[:8], "kind": kind, "label": label.strip(), "at": at.timestamp(),
            "message": message.strip(), "url": url, "created": time.time()}
    with store as data:
        data["items"].append(item)
    return item


def _items(kind=None):
    with store as data:
        items = sorted(data["items"], key=lambda i: i["at"])
    return [i for i in items if kind is None or i["kind"] == kind]


def _remove(ids):
    with store as data:
        data["items"] = [i for i in data["items"] if i["id"] not in ids]


def _describe(item, now=None):
    now = now or datetime.datetime.now()
    at = datetime.datetime.fromtimestamp(item["at"])
    if item["kind"] == "timer":
        left = max(0, item["at"] - time.time())
        name = (item["label"] + " timer") if item["label"] else "a timer"
        return "%s with %s left" % (name, duration_phrase(left))
    if item["kind"] == "alarm":
        return "an alarm%s at %s" % (" for " + item["label"] if item["label"] else "", clock_phrase(at, now))
    return "a reminder to %s at %s" % (item["message"], clock_phrase(at, now))


# ── Actions ──────────────────────────────────────────────────────────────────

@action("set_timer", "Countdown timer.", "minutes: number, label?: str")
def set_timer(minutes=0, seconds=0, label=""):
    try:
        total = float(minutes or 0) * 60 + float(seconds or 0)
    except (TypeError, ValueError):
        total = parse_duration("%s %s" % (minutes, seconds)) or 0
    if total <= 0:
        raise ActionError("How long should the timer be?")
    _add("timer", datetime.datetime.now() + datetime.timedelta(seconds=total), label=label)
    return "%s timer started." % duration_phrase(total).capitalize() if not label else \
        "%s timer for %s started." % (duration_phrase(total).capitalize(), label)


@action("set_alarm", "Alarm.", "time: str like '7:30 am', 'tomorrow 6 pm' or ISO, label?: str")
def set_alarm(time="", label=""):
    at, _ = parse_when(time)
    if not at:
        raise ActionError("What time should the alarm be?")
    _add("alarm", at, label=label)
    return "Alarm set for %s." % clock_phrase(at)


@action("set_reminder", "Reminder, optionally repeating.", "message: str, time?: str, minutes?: number, repeat_minutes?: number")
def set_reminder(message="", time=None, minutes=None, repeat_minutes=None):
    try:
        repeat = float(repeat_minutes) if repeat_minutes else 0.0
    except (TypeError, ValueError):
        repeat = 0.0
    at = None
    if minutes or (repeat and not time):
        try:
            at = datetime.datetime.now() + datetime.timedelta(minutes=float(minutes or repeat))
        except (TypeError, ValueError):
            at = None
    if at is None and time:
        at, _ = parse_when(str(time))
    if at is None:
        raise ActionError("When should I remind you?")
    message = (message or "").strip().rstrip(".") or "the thing you asked about"
    item = _add("reminder", at, message=message)
    if repeat >= 1:
        with store as data:
            for i in data["items"]:
                if i["id"] == item["id"]:
                    i["repeat_minutes"] = repeat
        return "I'll remind you to %s every %s, starting at %s." % (
            message, duration_phrase(repeat * 60), clock_phrase(at))
    return "I'll remind you to %s at %s." % (message, clock_phrase(at))


def parse_reminder(text):
    """'remind me to call mom in 10 minutes' -> ('call mom', datetime), or None."""
    t = normalize_time_words(text)
    at, _ = parse_when(t)
    if not at:
        return None
    msg = re.sub(r"^.*?\bremind me\b\s*", "", t)
    msg = re.sub(r"\b(?:in|after)\s+(?:\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)\s*(?:and\s*)?)+", "", msg)
    msg = re.sub(r"(?:\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)\s*)+from now", "", msg)
    msg = re.sub(r"\b(?:at|by|on)?\s*(?:today|tonight|tomorrow|%s)?\s*(?:at\s*)?\d{1,2}(?:[:.]\d{2}| \d{2})?\s*(?:am|pm)?\b"
                 % "|".join(WEEKDAYS), " ", msg)
    msg = re.sub(r"\b(?:today|tonight|tomorrow|noon|midnight)\b", " ", msg)
    msg = re.sub(r"^\s*(?:to|about|that|of)\s+", "", msg.strip())
    msg = re.sub(r"\s+(?:to|at|on|by)$", "", msg.strip())
    msg = re.sub(r"\s+", " ", msg).strip(" ,.")
    if not msg:
        return None
    msg = re.sub(r"\bmy\b", "your", msg)
    return msg, at


@action("list_timers", "List timers, alarms and reminders.")
def list_timers():
    items = _items()
    if not items:
        return "You have no timers, alarms or reminders."
    now = datetime.datetime.now()
    descs = [_describe(i, now) for i in items[:6]]
    more = " and %d more" % (len(items) - 6) if len(items) > 6 else ""
    return "You have " + ", ".join(descs) + more + "."


@action("time_left", "How long is left on a timer.", "label?: str", ai=False)
def time_left(label=""):
    timers = _items("timer")
    if label:
        timers = [t for t in timers if label.lower() in t["label"].lower()] or timers
    if not timers:
        return "No timers are running."
    t = timers[0]
    return "%s left%s." % (duration_phrase(max(0, t["at"] - time.time())).capitalize(),
                           " on the " + t["label"] + " timer" if t["label"] else "")


@action("cancel_timer", "Cancel a timer, alarm or reminder.", "match?: str, kind?: timer|alarm|reminder, all?: bool")
def cancel_timer(match="", kind=None, all=False):
    items = _items(kind if kind in ("timer", "alarm", "reminder") else None)
    if not items:
        return "There's nothing to cancel."
    if all:
        _remove({i["id"] for i in items})
        return "Cancelled %d item%s." % (len(items), "" if len(items) == 1 else "s")
    if match:
        m = match.lower()
        hits = [i for i in items if m in (i["label"] + " " + i["message"]).lower()]
        if not hits:
            return "I couldn't find one matching %s." % match
        target = hits[0]
    else:
        target = max(items, key=lambda i: i["created"])
    _remove({target["id"]})
    return "Cancelled " + _describe(target) + "."


@action("snooze_alarm", "Snooze what just went off.", "minutes?: number")
def snooze_alarm(minutes=9):
    last = svc.scheduler.last_fired if svc.scheduler else None
    if not last or time.time() - last[1] > 600:
        return "Nothing has gone off recently."
    item = last[0]
    at = datetime.datetime.now() + datetime.timedelta(minutes=float(minutes or 9))
    if item["kind"] == "event":
        _add("reminder", at, message=item["message"] or item["label"])
    else:
        _add(item["kind"], at, label=item["label"], message=item["message"])
    return "Snoozed until %s." % clock_phrase(at)


def _schedule():
    with store as data:
        return list(data.get("schedule") or [])


def _class_dt(entry, day_offset, now):
    h, m = map(int, entry["time"].split(":"))
    d = now + datetime.timedelta(days=day_offset)
    return d.replace(hour=h, minute=m, second=0, microsecond=0)


@action("schedule_list", "Weekly class schedule.", "day?: today|tomorrow|<weekday>|week")
def schedule_list(day="today"):
    now = datetime.datetime.now()
    day = (day or "today").lower()
    entries = _schedule()
    if day == "week":
        if not entries:
            return "Your weekly schedule is empty."
        return " ".join("%s on %s at %s." % (e["name"].capitalize(), " and ".join(d.capitalize() for d in e["days"]),
                                             _class_dt(e, 0, now).strftime("%I:%M %p").lstrip("0")) for e in entries)
    if day in ("today", "tomorrow"):
        offset = 0 if day == "today" else 1
    elif day in WEEKDAYS:
        offset = (WEEKDAYS.index(day) - now.weekday()) % 7
    else:
        offset = 0
    weekday = WEEKDAYS[(now.weekday() + offset) % 7]
    todays = sorted((e for e in entries if weekday in e.get("days", [])), key=lambda e: e["time"])
    label = day if day in ("today", "tomorrow") else "on " + weekday.capitalize()
    if not todays:
        return "Nothing on your schedule %s." % label
    parts = ["%s at %s" % (e["name"], _class_dt(e, offset, now).strftime("%I:%M %p").lstrip("0")) for e in todays]
    return "%s you have %s." % (label.capitalize(), ", then ".join(parts))


@action("next_class", "Next scheduled class.")
def next_class():
    now = datetime.datetime.now()
    best = None
    for e in _schedule():
        for offset in range(0, 8):
            wd = WEEKDAYS[(now.weekday() + offset) % 7]
            if wd in e.get("days", []):
                dt = _class_dt(e, offset, now)
                if dt > now and (best is None or dt < best[0]):
                    best = (dt, e)
    if not best:
        return "You have nothing scheduled."
    dt, e = best
    mins = (dt - now).total_seconds()
    when = "in " + duration_phrase(mins - mins % 60) if mins < 3 * 3600 else clock_phrase(dt, now)
    return "%s is %s." % (e["name"].capitalize(), when)


@action("schedule_add", "Add a weekly class or event.", "name: str, days: [weekday], time: str, url?: str")
def schedule_add(name="", days=None, time="", url="", message=""):
    if isinstance(days, str):
        days = re.findall("|".join(WEEKDAYS + ["weekdays", "weekends", "everyday", "every day", "daily"]), days.lower())
    days = [d.lower() for d in (days or [])]
    expanded = []
    for d in days:
        if d == "weekdays":
            expanded += WEEKDAYS[:5]
        elif d == "weekends":
            expanded += WEEKDAYS[5:]
        elif d in ("everyday", "every day", "daily"):
            expanded += WEEKDAYS
        elif d in WEEKDAYS:
            expanded.append(d)
    days = sorted(set(expanded), key=WEEKDAYS.index)
    at, _ = parse_when(time)
    if not name or not days or not at:
        raise ActionError("I need a name, the days and a time for that.")
    if url == "clipboard":
        from ..winapi import get_clipboard
        url = get_clipboard().strip()
    entry = {"name": name.lower(), "days": days, "time": at.strftime("%H:%M"),
             "message": message or "Time for %s." % name, "url": url if str(url).startswith("http") else None}
    with store as data:
        data["schedule"].append(entry)
    return "Added %s on %s at %s." % (name, " and ".join(d.capitalize() for d in days),
                                      at.strftime("%I:%M %p").lstrip("0"))


@action("schedule_remove", "Remove a weekly event.", "name: str")
def schedule_remove(name=""):
    with store as data:
        before = len(data["schedule"])
        data["schedule"] = [e for e in data["schedule"] if name.lower() not in e["name"].lower()]
        removed = before - len(data["schedule"])
    return "Removed %s from your schedule." % name if removed else "I couldn't find %s on your schedule." % name


# ── Background scheduler ─────────────────────────────────────────────────────

class Scheduler:
    def __init__(self, cfg):
        self.cfg = cfg
        self.last_fired = None
        self._fired_schedule = set()
        self._last_break = time.time()
        self._focus_break_until = 0.0
        _migrate()

    def start(self):
        self._missed()
        threading.Thread(target=self._run, name="scheduler", daemon=True).start()

    def _missed(self):
        now = time.time()
        due = [i for i in _items() if i["at"] <= now]
        if not due:
            return
        _remove({i["id"] for i in due})
        for i in due:
            if i.get("repeat_minutes"):
                self._reschedule(i)
        recent = [i for i in due if now - i["at"] < 12 * 3600 and i["kind"] == "reminder" and not i.get("repeat_minutes")]
        if recent:
            msgs = ", ".join(i["message"] for i in recent)
            notify("Missed reminders", "While I was off, you had reminders to " + msgs + ".", speak=False)

    @staticmethod
    def _reschedule(item):
        nxt = _add(item["kind"], datetime.datetime.now() + datetime.timedelta(minutes=item["repeat_minutes"]),
                   label=item["label"], message=item["message"], url=item.get("url"))
        with store as data:
            for i in data["items"]:
                if i["id"] == nxt["id"]:
                    i["repeat_minutes"] = item["repeat_minutes"]

    def _fire(self, item):
        if item.get("repeat_minutes"):
            self._reschedule(item)
        if item["kind"] == "timer":
            msg = "Your %s timer is done." % item["label"] if item["label"] else "Time's up."
            sound = "alarm"
        elif item["kind"] == "alarm":
            at = datetime.datetime.fromtimestamp(item["at"])
            msg = "It's %s.%s" % (at.strftime("%I:%M %p").lstrip("0"), " " + item["label"].capitalize() + "." if item["label"] else "")
            sound = "alarm"
        else:
            msg = "Reminder: %s." % item["message"]
            sound = "soft"
        self.last_fired = (item, time.time())
        play = sound if self.cfg["reminders"].get("alarm_sound", True) else None
        notify("Gem", msg, sound=play)
        if item.get("url"):
            webbrowser.open(item["url"])

    def _fire_event(self, item):
        self.last_fired = (item, time.time())
        notify("Gem", item["message"] or "Time for %s." % item["label"], sound="alarm")
        if item.get("url"):
            webbrowser.open(item["url"])

    def _breaks(self):
        minutes = float(self.cfg["reminders"].get("break_minutes") or 0)
        st = svc.state
        if minutes <= 0:
            return
        if idle_seconds() > 300:          # away from the PC: restart the clock
            self._last_break = time.time()
            return
        if time.time() - self._last_break < minutes * 60:
            return
        self._last_break = time.time()
        if st.focusing or st.quiet_alerts():
            return
        notify("Break", self.cfg["reminders"].get("break_message", "Time for a quick break."), speak=False)

    def _focus(self):
        st = svc.state
        now = time.time()
        if st.focus_until and now >= st.focus_until:
            st.update(focus_until=0.0)
            brk = float(self.cfg["focus"].get("break_minutes", 5))
            self._focus_break_until = now + brk * 60
            notify("Focus", "Focus session done. Take a %g minute break." % brk, sound="soft")
        if self._focus_break_until and now >= self._focus_break_until:
            self._focus_break_until = 0.0
            notify("Focus", "Break's over.", sound="soft")

    def _snooze(self):
        st = svc.state
        if st.snoozed_until and not st.ruhig and time.time() >= st.snoozed_until:
            st.update(snoozed_until=0.0)
            caption("I'm back.")
            if svc.lights:
                svc.lights.flash("ack")

    def _run(self):
        last_minute = None
        while True:
            try:
                now = time.time()
                due = [i for i in _items() if i["at"] <= now]
                if due:
                    _remove({i["id"] for i in due})
                    for item in due:
                        self._fire(item)
                dt = datetime.datetime.now()
                minute = dt.strftime("%H%M")
                if minute != last_minute:
                    last_minute = minute
                    self._check_schedule_events(dt)
                self._breaks()
                self._focus()
                self._snooze()
            except Exception:
                log.exception("Scheduler tick failed")
            time.sleep(1)

    def _check_schedule_events(self, now):
        day = WEEKDAYS[now.weekday()]
        hhmm = now.strftime("%H:%M")
        for e in _schedule():
            if day in e.get("days", []) and e.get("time") == hhmm:
                key = "%s_%s" % (e["name"], now.strftime("%Y%m%d%H%M"))
                if key not in self._fired_schedule:
                    self._fired_schedule.add(key)
                    self._fire_event({"kind": "event", "label": e["name"], "message": e.get("message") or "",
                                      "url": e.get("url")})
