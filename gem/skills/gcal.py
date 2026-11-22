"""Google Calendar, read only, from its secret iCal link (Google Calendar: Settings, your calendar, "Secret address
in iCal format"; pasted into Gem's Settings, under You). Gem fetches it every 15 minutes: what's on today or
tomorrow, what's next, today's events in the briefing, the next one on the island, and a heads-up before each.

The link is a password for reading the calendar: it stays in settings.json and is never logged.
"""
import datetime
import logging
import threading
import time

import requests

from .. import nettime
from ..actions import ActionError, action
from ..cards import card
from ..parse import WEEKDAYS
from ..runtime import notify, svc

log = logging.getLogger("gem.gcal")

REFRESH = 900
_cal = {"data": None, "feed": "", "soon": None}     # parsed calendar, the link it came from, next event soon
_warned = set()                                      # (title, start) already given a heads-up


def cfg():
    return (svc.config or {}).get("calendar") or {}


def _feed():
    return (cfg().get("feed") or "").strip()


def _fetch():
    import icalendar
    feed = _feed()
    r = requests.get(feed.replace("webcal://", "https://", 1), timeout=20)
    r.raise_for_status()
    _cal.update(data=icalendar.Calendar.from_ical(r.content), feed=feed)


def _local(v):
    """A start or end as a naive local datetime; an all-day date becomes its midnight."""
    if isinstance(v, datetime.datetime):
        return v.astimezone().replace(tzinfo=None) if v.tzinfo else v
    return datetime.datetime.combine(v, datetime.time())


def events(start, end):
    """[(start, end, title, all_day)] overlapping [start, end), earliest first, from the last fetch."""
    if _cal["data"] is None:
        return []
    import recurring_ical_events
    out = []
    for ev in recurring_ical_events.of(_cal["data"]).between(start, end):
        if str(ev.get("status", "")).upper() == "CANCELLED":
            continue
        first = ev.decoded("dtstart")
        s = _local(first)
        e = _local(ev.decoded("dtend")) if "DTEND" in ev else s
        out.append((s, e, str(ev.get("summary") or "Event").strip(), not isinstance(first, datetime.datetime)))
    return sorted(out, key=lambda x: (not x[3], x[0]))       # all-day ones first, then by time


def _ready():
    """Fetch now if there's nothing yet (or the link changed). Raises ActionError when it can't be had."""
    if not _feed():
        raise ActionError("Your calendar isn't connected. Paste its secret iCal link in Gem's Settings, under You.")
    if _cal["data"] is None or _cal["feed"] != _feed():
        try:
            _fetch()
        except Exception as e:
            log.warning("Calendar fetch failed: %s", type(e).__name__)
            if _cal["data"] is None:
                raise ActionError("I couldn't reach your calendar right now.")


def _when(s, all_day):
    return "all day" if all_day else s.strftime("%I:%M %p").lstrip("0")


@action("calendar_events", "Events on the user's Google Calendar for a day, or the next one coming up.",
        "day?: today|tomorrow|<weekday>|next")
def calendar_events(day="today"):
    _ready()
    now = nettime.now()
    day = (day or "today").lower().replace("on ", "").strip()
    if day == "next":
        coming = [ev for ev in events(now, now + datetime.timedelta(days=14)) if not ev[3] and ev[0] >= now]
        if not coming:
            return card("schedule", "Nothing coming up on your calendar in the next two weeks.", title="Calendar",
                        rows=[])
        s, _, title, _ = coming[0]
        from ..parse import clock_phrase
        return card("schedule", "Next on your calendar: %s, at %s." % (title, clock_phrase(s, now)), title="Next",
                    rows=[{"time": _when(s, False), "name": title, "next": True}])
    if day in WEEKDAYS:
        offset = (WEEKDAYS.index(day) - now.weekday()) % 7 or 7
    else:
        offset = 1 if day == "tomorrow" else 0
        day = "tomorrow" if offset else "today"
    start = datetime.datetime.combine(now.date(), datetime.time()) + datetime.timedelta(days=offset)
    evs = events(start, start + datetime.timedelta(days=1))
    label = day if day in ("today", "tomorrow") else "on " + day.capitalize()
    if not evs:
        return card("schedule", "Nothing on your calendar %s." % label, title="Calendar", rows=[])
    parts = ["%s %s" % (t, "all day" if all_day else "at " + _when(s, False)) for s, _, t, all_day in evs]
    nxt = next(((s, t) for s, _, t, all_day in evs if not all_day and s > now), None)
    rows = [{"time": _when(s, all_day), "name": t, "next": (s, t) == nxt} for s, _, t, all_day in evs]
    return card("schedule", "%s you have %s." % (label.capitalize(), ", then ".join(parts)), title="Calendar",
                rows=rows)


def today_lines(now):
    """[(time, title)] of today's events for the briefing; [] when there's no calendar."""
    if _cal["data"] is None:
        return []
    start = datetime.datetime.combine(now.date(), datetime.time())
    return [(_when(s, all_day), t) for s, _, t, all_day in events(start, start + datetime.timedelta(days=1))]


def heads_up(now):
    """Every minute, from the scheduler: the heads-up before an event, and what's starting soon for the island."""
    if _cal["data"] is None:
        return
    minute = now.replace(second=0, microsecond=0)
    soon = [ev for ev in events(minute, minute + datetime.timedelta(minutes=16)) if not ev[3] and ev[0] >= minute]
    _cal["soon"] = (soon[0][2], soon[0][0]) if soon else None
    mins = int(cfg().get("remind_minutes", 10) or 0)
    for s, _, title, _ in soon:
        if mins and minute + datetime.timedelta(minutes=mins) <= s < minute + datetime.timedelta(minutes=mins + 1) \
                and (title, s) not in _warned:
            _warned.add((title, s))
            notify(title, "%s starts in %d minutes." % (title, mins), sound="soft")


def upcoming(within_minutes=15):
    """(title, start) of an event starting within the next N minutes, else None (for the island)."""
    soon = _cal["soon"]
    if soon and nettime.now() <= soon[1] <= nettime.now() + datetime.timedelta(minutes=within_minutes):
        return soon
    return None


def _loop():
    last = -REFRESH
    while True:
        if _feed() and (time.monotonic() - last >= REFRESH or _cal["feed"] != _feed()):   # due, or a new link
            last = time.monotonic()
            try:
                _fetch()
            except Exception as e:
                log.warning("Calendar refresh failed: %s", type(e).__name__)
        time.sleep(60)


def start():
    threading.Thread(target=_loop, name="gcal", daemon=True).start()
