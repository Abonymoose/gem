"""Time zones, a world clock, and countdowns to dates and holidays."""
import datetime
import logging
import re
from zoneinfo import ZoneInfo

import requests

from ..actions import ActionError, action
from ..cards import card
from ..config import JsonStore
from ..parse import normalize_time_words, parse_when

log = logging.getLogger("gem.world")

store = JsonStore("world.json", {"clocks": [], "dates": {}})

ZONES = {
    "utc": "UTC", "gmt": "UTC", "zulu": "UTC",
    "est": "America/New_York", "edt": "America/New_York", "et": "America/New_York", "eastern": "America/New_York",
    "eastern time": "America/New_York", "new york": "America/New_York", "nyc": "America/New_York",
    "cst": "America/Chicago", "cdt": "America/Chicago", "central": "America/Chicago", "central time": "America/Chicago",
    "mst": "America/Denver", "mdt": "America/Denver", "mountain": "America/Denver",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles", "pacific time": "America/Los_Angeles", "la": "America/Los_Angeles",
    "ist": "Asia/Kolkata", "india": "Asia/Kolkata", "indian time": "Asia/Kolkata",
    "bst": "Europe/London", "uk": "Europe/London", "britain": "Europe/London", "england": "Europe/London",
    "cet": "Europe/Paris", "cest": "Europe/Paris", "europe": "Europe/Paris", "eet": "Europe/Athens",
    "jst": "Asia/Tokyo", "japan": "Asia/Tokyo", "kst": "Asia/Seoul", "korea": "Asia/Seoul",
    "aest": "Australia/Sydney", "aedt": "Australia/Sydney", "awst": "Australia/Perth",
    "nzst": "Pacific/Auckland", "nzdt": "Pacific/Auckland", "sgt": "Asia/Singapore", "hkt": "Asia/Hong_Kong",
    "gst": "Asia/Dubai", "uae": "Asia/Dubai", "pkt": "Asia/Karachi", "china": "Asia/Shanghai", "cst china": "Asia/Shanghai",
    "brt": "America/Sao_Paulo", "brazil": "America/Sao_Paulo", "canada": "America/Toronto", "usa": "America/New_York",
    "america": "America/New_York", "us": "America/New_York",
}
HERE_WORDS = {"here", "my time", "my", "mine", "our", "ours", "local", "local time", "my timezone", "my time zone",
              "home", "me", "where i am", "where i live", "my place", "my zone"}
_geo = {}


def local_zone():
    return datetime.datetime.now().astimezone().tzinfo


def resolve(place):
    """(display name, tzinfo) for a city, country, abbreviation or 'here'."""
    p = re.sub(r"\s+time$", "", (place or "").lower().strip(" ?.")).strip()
    p = re.sub(r"^(?:the )", "", p)
    if not p or p in HERE_WORDS:
        return "Here", local_zone()
    if p in ZONES:
        name = p.upper() if len(p) <= 4 else p.title()
        return name, ZoneInfo(ZONES[p])
    if p in _geo:
        return _geo[p]
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": p, "count": 1, "language": "en"}, timeout=6).json()
        hit = (r.get("results") or [None])[0]
    except Exception:
        hit = None
    if not hit or not hit.get("timezone"):
        raise ActionError("I don't know the time zone for %s." % place)
    _geo[p] = (hit["name"], ZoneInfo(hit["timezone"]))
    return _geo[p]


def _offset_phrase(a, b, when):
    """How far zone b is from zone a at `when`, e.g. '+9h 30m'."""
    diff = (when.astimezone(b).utcoffset() - when.astimezone(a).utcoffset()).total_seconds() / 60
    if diff == 0:
        return "same time"
    sign = "+" if diff > 0 else "-"
    h, m = divmod(int(abs(diff)), 60)
    return "%s%dh%s" % (sign, h, " %dm" % m if m else "")


def _day_label(dt, ref):
    delta = (dt.date() - ref.date()).days
    return {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get(delta, dt.strftime("%a"))


def _clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


@action("time_in", "Current time in a city, country or time zone.", "place: str")
def time_in(place=""):
    name, tz = resolve(place)
    now = datetime.datetime.now().astimezone()
    there = now.astimezone(tz)
    day = _day_label(there, now)
    off = _offset_phrase(local_zone(), tz, now)
    day_txt = "" if day == "Today" else " %s" % day.lower()
    span = off.lstrip("+-").replace("h", " hours").replace("m", " minutes").replace("1 hours", "1 hour")
    ahead = "" if off == "same time" else (", %s ahead of you" % span if off.startswith("+") else ", %s behind you" % span)
    return card("world", "It's %s%s in %s%s." % (_clock(there), day_txt, name, ahead),
                rows=[{"place": name, "time": _clock(there), "day": day, "offset": off}])


@action("time_convert", "Convert a time between zones, e.g. '3 pm' from 'est' to 'ist' (to defaults to here).",
        "time: str, from_place: str, to_place?: str")
def time_convert(time="", from_place="", to_place="here"):
    src_name, src = resolve(from_place)
    dst_name, dst = resolve(to_place or "here")
    base, _ = parse_when(normalize_time_words(time))
    if base is None:
        raise ActionError("What time should I convert?")
    there = datetime.datetime.now(src)
    when = there.replace(hour=base.hour, minute=base.minute, second=0, microsecond=0)
    converted = when.astimezone(dst)
    day = _day_label(converted, when)
    day_txt = "" if day == "Today" else " (%s)" % ("next day" if day == "Tomorrow" else "previous day" if day == "Yesterday"
                                                   else day)
    src_txt = "your time" if src_name == "Here" else "in " + src_name
    dst_txt = "your time" if dst_name == "Here" else "in " + dst_name
    return card("world", "%s %s is %s%s %s." % (_clock(when), src_txt, _clock(converted), day_txt, dst_txt),
                rows=[{"place": src_name, "time": _clock(when), "day": "", "offset": ""},
                      {"place": dst_name, "time": _clock(converted), "day": "" if day == "Today" else day,
                       "offset": _offset_phrase(src, dst, when)}])


@action("world_clock", "Show the user's world clock, or add/remove a place.", "add?: str, remove?: str")
def world_clock(add="", remove=""):
    if add:
        name, tz = resolve(add)
        with store as data:
            if not any(c["name"].lower() == name.lower() for c in data["clocks"]):
                data["clocks"].append({"name": name, "tz": tz.key})
        return "Added %s to your world clock." % name
    if remove:
        with store as data:
            before = len(data["clocks"])
            data["clocks"] = [c for c in data["clocks"] if remove.lower() not in c["name"].lower()]
            if len(data["clocks"]) == before:
                return "%s isn't on your world clock." % remove.title()
        return "Removed %s." % remove.title()
    clocks = store.data.get("clocks") or []
    if not clocks:
        return "Your world clock is empty. Say, add Tokyo to my world clock."
    now = datetime.datetime.now().astimezone()
    rows = []
    for c in clocks:
        t = now.astimezone(ZoneInfo(c["tz"]))
        rows.append({"place": c["name"], "time": _clock(t), "day": _day_label(t, now),
                     "offset": _offset_phrase(local_zone(), ZoneInfo(c["tz"]), now)})
    text = ". ".join("%s %s" % (r["place"], r["time"]) for r in rows) + "."
    return card("world", text, rows=rows)


# ── Countdowns ───────────────────────────────────────────────────────────────

def _nth_weekday(year, month, weekday, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(weekday - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


HOLIDAYS = {
    "christmas": lambda y: datetime.date(y, 12, 25), "christmas eve": lambda y: datetime.date(y, 12, 24),
    "new year": lambda y: datetime.date(y + 1, 1, 1) if datetime.date.today() >= datetime.date(y, 1, 2)
    else datetime.date(y, 1, 1),
    "new years": lambda y: HOLIDAYS["new year"](y), "new year's": lambda y: HOLIDAYS["new year"](y),
    "new year's eve": lambda y: datetime.date(y, 12, 31), "new years eve": lambda y: datetime.date(y, 12, 31),
    "halloween": lambda y: datetime.date(y, 10, 31), "valentine's day": lambda y: datetime.date(y, 2, 14),
    "valentines day": lambda y: datetime.date(y, 2, 14), "valentines": lambda y: datetime.date(y, 2, 14),
    "easter": _easter, "thanksgiving": lambda y: _nth_weekday(y, 11, 3, 4),
    "mother's day": lambda y: _nth_weekday(y, 5, 6, 2), "mothers day": lambda y: _nth_weekday(y, 5, 6, 2),
    "father's day": lambda y: _nth_weekday(y, 6, 6, 3), "fathers day": lambda y: _nth_weekday(y, 6, 6, 3),
    "independence day": lambda y: datetime.date(y, 8, 15), "republic day": lambda y: datetime.date(y, 1, 26),
    "summer": lambda y: datetime.date(y, 6, 21), "winter": lambda y: datetime.date(y, 12, 21),
}
# Lunar-calendar festivals move every year, so these are looked up.
FESTIVALS = {
    "diwali": {2026: (11, 8), 2027: (10, 29), 2028: (10, 17), 2029: (11, 5), 2030: (10, 26)},
    "holi": {2026: (3, 4), 2027: (3, 22), 2028: (3, 11), 2029: (3, 1), 2030: (3, 20)},
    "chinese new year": {2026: (2, 17), 2027: (2, 6), 2028: (1, 26), 2029: (2, 13), 2030: (2, 3)},
    "lunar new year": {2026: (2, 17), 2027: (2, 6), 2028: (1, 26), 2029: (2, 13), 2030: (2, 3)},
}
for _name, _dates in FESTIVALS.items():
    HOLIDAYS[_name] = (lambda dates: lambda y: datetime.date(y, *dates[y]) if y in dates else None)(_dates)
HOLIDAYS["deepavali"] = HOLIDAYS["diwali"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]


def parse_date(text):
    """A future date from speech: 'march 3rd', '3 march', '25/12', 'friday', 'next friday', '2026-12-01'."""
    t = (text or "").lower().strip(" ?.")
    today = datetime.date.today()
    try:
        return datetime.date.fromisoformat(t)
    except ValueError:
        pass
    mon = "|".join(MONTHS + [m[:3] for m in MONTHS])
    m = re.search(r"\b(%s)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b" % mon, t) or \
        re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(%s)\b" % mon, t)
    if m:
        a, b = m.groups()
        month_word, day = (a, int(b)) if not a.isdigit() else (b, int(a))
        month = next(i for i, name in enumerate(MONTHS, 1) if name.startswith(month_word[:3]))
        d = datetime.date(today.year, month, day)
        return d if d >= today else datetime.date(today.year + 1, month, day)
    from ..parse import WEEKDAYS
    m = re.search(r"\b(next |this )?(%s)\b" % "|".join(WEEKDAYS), t)
    if m:
        wd = WEEKDAYS.index(m.group(2))
        ahead = (wd - today.weekday()) % 7 or 7
        if m.group(1) == "next " and wd > today.weekday():
            ahead += 7          # "next friday" on a Tuesday is the one after this week's
        return today + datetime.timedelta(days=ahead)
    m = re.search(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", t)
    if m:
        day = int(m.group(1))
        d = today.replace(day=min(day, 28)) if day > 28 else today.replace(day=day)
        if d < today:
            d = (today.replace(day=1) + datetime.timedelta(days=32)).replace(day=day if day <= 28 else 28)
        return d
    return None


@action("save_date", "Remember a named date like a birthday or exam, for countdowns.", "name: str, date: str")
def save_date(name="", date=""):
    d = parse_date(date)
    if not name or not d:
        raise ActionError("I need a name and a date, like my birthday is March 3.")
    key = re.sub(r"^(?:my|the)\s+", "", name.lower().strip())
    with store as data:
        data["dates"][key] = {"month": d.month, "day": d.day, "year": d.year}
    shown = key[:1].upper() + key[1:] if "'s " in key else key
    return "Saved %s: %s." % (shown, d.strftime("%B %d").replace(" 0", " "))


@action("countdown", "How long until a date, holiday or saved date (birthday, exam...).", "to: str")
def countdown(to=""):
    t = re.sub(r"^(?:my|the)\s+", "", (to or "").lower().strip(" ?."))
    if not t:
        raise ActionError("Until when?")
    today = datetime.date.today()
    target, label = None, t
    saved = store.data.get("dates", {})
    if t in saved:
        s = saved[t]
        target = datetime.date(today.year, s["month"], s["day"])
        if target < today:
            target = datetime.date(today.year + 1, s["month"], s["day"])
        label = (t[:1].upper() + t[1:]) if "'s " in t else "your " + t       # "Aarav's birthday", "your exam"
    elif t in HOLIDAYS:
        target = HOLIDAYS[t](today.year)
        if target is None or target < today:
            target = HOLIDAYS[t](today.year + 1)
        if target is None:
            raise ActionError("I don't have the date for %s that far out." % t.title())
        label = t.title().replace("'S", "'s")
    else:
        target = parse_date(t)
        label = target.strftime("%A, %B %d").replace(" 0", " ") if target else t
    if not target:
        at, _ = parse_when(normalize_time_words(t))
        if at:
            left = (at - datetime.datetime.now()).total_seconds()
            from ..parse import duration_phrase
            return card("countdown", "%s is in %s." % (_clock(at), duration_phrase(left - left % 60 or left)),
                        days=0, label=_clock(at), date=duration_phrase(left - left % 60 or left), time_only=True)
        raise ActionError("I don't know when %s is. You can tell me, like my birthday is March 3." % to)
    days = (target - today).days
    when = target.strftime("%A, %B %d").replace(" 0", " ")
    if days == 0:
        text = "%s is today!" % label[0].upper() + label[1:]
    elif days == 1:
        text = "%s is tomorrow." % (label[0].upper() + label[1:])
    else:
        weeks = " That's about %d weeks." % round(days / 7) if days >= 21 else ""
        on = "" if label == when else ", on %s" % when
        text = "%s is in %d days%s.%s" % (label[0].upper() + label[1:], days, on, weeks)
    sub = when
    if label == when:
        # The date is already the title; say which week it falls in instead.
        wk = (target - (today - datetime.timedelta(days=today.weekday()))).days // 7
        sub = {0: "This week", 1: "Next week"}.get(wk, "In %d weeks" % wk)
    return card("countdown", text, days=days, label=label, date=sub)
