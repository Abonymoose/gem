"""Habit tracker: "I drank water", "log 20 pushups", "how much water today"."""
import datetime
import re

from ..actions import ActionError, action
from ..cards import card
from ..config import JsonStore

store = JsonStore("habits.json", {"log": {}})

ALIASES = {"glass of water": "water", "glasses of water": "water", "cup of water": "water", "cups of water": "water",
           "bottle of water": "water", "bottles of water": "water", "waters": "water", "push ups": "pushups",
           "push-ups": "pushups", "pushup": "pushups", "push up": "pushups", "sit ups": "situps", "sit-ups": "situps",
           "situp": "situps", "coffees": "coffee", "cups of coffee": "coffee", "cup of coffee": "coffee",
           "teas": "tea", "cups of tea": "tea", "cup of tea": "tea", "squat": "squats", "page": "pages",
           "minutes of exercise": "exercise", "minutes exercise": "exercise", "workout": "exercise"}
UNITS = {"water": ("glass", "glasses"), "coffee": ("cup", "cups"), "tea": ("cup", "cups"),
         "pushups": ("push-up", "push-ups"), "situps": ("sit-up", "sit-ups"), "squats": ("squat", "squats"),
         "pages": ("page", "pages"), "exercise": ("minute", "minutes")}


def habit_key(name):
    n = re.sub(r"\s+", " ", (name or "").lower().strip())
    n = re.sub(r"^(?:a |an |some |more |another )", "", n)
    return ALIASES.get(n, n)


def _unit(key, n):
    one, many = UNITS.get(key, (key, key))
    return one if n == 1 else many


def _days(key, count=7):
    log = store.data.get("log", {}).get(key, {})
    today = datetime.date.today()
    out = []
    for i in range(count - 1, -1, -1):
        d = today - datetime.timedelta(days=i)
        out.append((d.strftime("%a")[0], log.get(d.isoformat(), 0)))
    return out


def _streak(key):
    log = store.data.get("log", {}).get(key, {})
    d, n = datetime.date.today(), 0
    if not log.get(d.isoformat()):
        d -= datetime.timedelta(days=1)
    while log.get(d.isoformat()):
        n += 1
        d -= datetime.timedelta(days=1)
    return n


def _card(key, text):
    days = _days(key)
    return card("habit", text, habit=key, today=days[-1][1], unit=_unit(key, days[-1][1]), days=days,
                streak=_streak(key))


@action("habit_log", "Log a habit, e.g. water (glasses), pushups, coffee, pages, exercise (minutes).",
        "habit: str, amount?: number")
def habit_log(habit="", amount=1):
    key = habit_key(habit)
    if not key:
        raise ActionError("What should I log?")
    try:
        amount = max(1, int(float(amount or 1)))
    except (TypeError, ValueError):
        amount = 1
    today = datetime.date.today().isoformat()
    with store as data:
        day = data.setdefault("log", {}).setdefault(key, {})
        day[today] = day.get(today, 0) + amount
        total = day[today]
    return _card(key, "Logged. That's %d %s today." % (total, _unit(key, total)))


@action("habit_stats", "How much of a habit the user has logged today and this week.", "habit: str")
def habit_stats(habit=""):
    key = habit_key(habit)
    days = _days(key)
    if not any(v for _, v in days):
        return "You haven't logged any %s this week." % _unit(key, 2)
    week = sum(v for _, v in days)
    streak = _streak(key)
    extra = " You're on a %d-day streak." % streak if streak > 1 else ""
    return _card(key, "%d %s today, %d this week.%s" % (days[-1][1], _unit(key, days[-1][1]), week, extra))
