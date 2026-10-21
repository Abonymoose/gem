"""Activity timeline: which app or site you were in, and when. "What was I doing at 3?", "when did I start
Valorant?", "how long have I been playing?", "show my timeline for yesterday".

Built from the same local samples as screen time (the foreground window every few seconds, only while you're
active). Window titles are kept with it so answers can say which video or document; everything stays in the
data folder and is dropped after two weeks.
"""
import datetime
import logging
import re
import threading
import time

from ..actions import ActionError, action
from ..cards import card
from ..config import JsonStore
from ..parse import duration_phrase, normalize_time_words, parse_duration

log = logging.getLogger("gem.timeline")

store = JsonStore("timeline.json", {"days": {}, "open": None})
KEEP_DAYS = 14
GAP = 150               # seconds without a sample (away, locked) that end a stretch
SHORTEST = 10           # stretches shorter than this are alt-tab flicker
MERGE_GAP = 180         # stretches of the same app this close together read as one
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
BROWSER_TAIL = re.compile(r"\s+[-—|]\s+(?:(?:Personal|Work|Profile \d+)\s+-\s+)?(?:Google Chrome|Brave|"
                          r"Mozilla Firefox|Microsoft​?\s?Edge|Opera)$")

_open = None            # the stretch in progress: {"s", "e", "app", "titles": [[t, title], ...]}
_closed = []
_lock = threading.Lock()


def _clean(title):
    title = BROWSER_TAIL.sub("", (title or "").strip())
    title = re.sub(r"\s+and \d+ more pages?$", "", title)
    return title[:90]


_restored = [False]


def _restore():
    """Once per run: the stretch Gem was in when it last closed becomes a finished one."""
    if _restored[0]:
        return
    _restored[0] = True
    with store as d:
        last = d.pop("open", None)
        if last and last.get("e", 0) - last.get("s", 0) >= SHORTEST:
            day = datetime.date.fromtimestamp(last["s"]).isoformat()
            d.setdefault("days", {}).setdefault(day, []).append(last)


def sample(app, title, now, interval):
    """Called by the screen time tracker for every sample of the foreground window."""
    global _open
    title = _clean(title)
    with _lock:
        _restore()
        if _open and _open["app"] == app and now - _open["e"] <= GAP:
            _open["e"] = now
            if title and (not _open["titles"] or _open["titles"][-1][1] != title):
                _open["titles"].append([round(now), title])
                if len(_open["titles"]) > 24:
                    del _open["titles"][1]              # keep the first title and the latest ones
            return
        if _open and _open["e"] - _open["s"] >= SHORTEST:
            _closed.append(_open)
        _open = {"s": round(now - interval), "e": now, "app": app, "titles": [[round(now), title]] if title else []}


def flush():
    with _lock:
        _restore()
        closed, _closed[:] = list(_closed), []
        current = dict(_open, titles=list(_open["titles"])) if _open else None
    with store as d:
        days = d.setdefault("days", {})
        for seg in closed:
            seg["e"] = round(seg["e"])
            days.setdefault(datetime.date.fromtimestamp(seg["s"]).isoformat(), []).append(seg)
        d["open"] = dict(current, e=round(current["e"])) if current else None
        cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
        for day in [k for k in days if k < cutoff]:
            days.pop(day)


def _segments(start, end):
    """Stretches overlapping [start, end], oldest first, including the one in progress."""
    with _lock:
        live = [dict(s) for s in _closed] + ([dict(_open)] if _open else [])
    saved = store.data.get("days") or {}
    out = []
    day = datetime.date.fromtimestamp(start) - datetime.timedelta(days=1)
    while day <= datetime.date.fromtimestamp(end):
        out += saved.get(day.isoformat(), [])
        day += datetime.timedelta(days=1)
    if store.data.get("open") and not _restored[0]:
        out.append(store.data["open"])          # from the last run, not filed yet
    out += live
    seen, result = set(), []
    for s in sorted(out, key=lambda s: s["s"]):
        if s["e"] >= start and s["s"] <= end and (s["s"], s["app"]) not in seen:
            seen.add((s["s"], s["app"]))
            result.append(s)
    return result


def _blocks(segs):
    """Join stretches of the same app with short gaps (or a quick look at something else) between them."""
    out = []
    for i, s in enumerate(segs):
        nxt = segs[i + 1] if i + 1 < len(segs) else None
        if s["e"] - s["s"] < 60 and out and nxt and nxt["app"] == out[-1]["app"] \
                and nxt["s"] - out[-1]["e"] <= MERGE_GAP:
            continue
        if out and out[-1]["app"] == s["app"] and s["s"] - out[-1]["e"] <= MERGE_GAP:
            out[-1]["e"] = max(out[-1]["e"], s["e"])
            out[-1]["titles"] = out[-1]["titles"] + s.get("titles", [])
        else:
            out.append(dict(s, titles=list(s.get("titles", []))))
    return out


def _title_at(seg, t):
    titles = [x for x in seg.get("titles") or [] if x[0] <= t + 5] or (seg.get("titles") or [])[:1]
    title = titles[-1][1] if titles else ""
    title = re.sub(r"\s+[-—|·]\s+%s$" % re.escape(seg["app"]), "", title, flags=re.I).strip()
    return "" if not title or title.lower() == seg["app"].lower() else title


def _day_of(dt):
    """Days run 5 AM to 5 AM, so late nights count with the evening before."""
    return (dt - datetime.timedelta(hours=5)).date()


def _day_start(d):
    return datetime.datetime.combine(d, datetime.time(5)).timestamp()


def _clock(t):
    return datetime.datetime.fromtimestamp(t).strftime("%I:%M %p").lstrip("0")


def _ago(t):
    secs = time.time() - t
    return "just now" if secs < 90 else "%s ago" % duration_phrase(int(secs // 60) * 60)


def _day_name(d):
    today = _day_of(datetime.datetime.now())
    return "today" if d == today else "yesterday" if d == today - datetime.timedelta(days=1) else d.strftime("%A")


def past_time(text, now=None):
    """A moment in the past from speech: "at 3", "3:30 pm", "an hour ago", "yesterday at 5", "on monday at noon"."""
    now = now or datetime.datetime.now()
    t = normalize_time_words((text or "").lower())
    m = re.search(r"\b(.+?)\s+ago\b", t)
    if m:
        secs = parse_duration(m.group(1))
        if secs:
            return now - datetime.timedelta(seconds=secs)
    offset = None
    if re.search(r"\byesterday\b|\blast night\b", t):
        offset = 1
    else:
        wm = re.search(r"\b(%s)\b" % "|".join(WEEKDAYS), t)
        if wm:
            offset = (now.weekday() - WEEKDAYS.index(wm.group(1))) % 7 or 7
    tm = re.search(r"\b(\d{1,2})(?::|\.|\s)(\d{2})\s*(am|pm)?\b", t) or re.search(r"\b(\d{1,2})()\s*(am|pm)\b", t) \
        or re.search(r"\b(?:at|around|about|by)\s+(\d{1,2})()()\b(?!\s*(?:minutes?|mins?|hours?))", t) \
        or re.search(r"^(\d{1,2})()()$", t.strip())
    if tm:
        hour, minute, ampm = int(tm.group(1)), int(tm.group(2) or 0), tm.group(3)
    elif re.search(r"\b(?:noon|midday|lunch ?time)\b", t):
        hour, minute, ampm = 12, 0, "pm"
    elif re.search(r"\bmidnight\b", t):
        hour, minute, ampm, offset = 0, 0, "am", offset if offset is not None else 0
    elif "last night" in t:
        hour, minute, ampm = 22, 0, None
    else:
        return None
    if hour > 23 or minute > 59:
        return None
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    base = (now - datetime.timedelta(days=offset or 0)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if ampm or hour > 12:
        return base if offset is not None or base <= now else base - datetime.timedelta(days=1)
    if offset is not None:
        return base + datetime.timedelta(hours=12) if 1 <= hour < 8 else base     # "yesterday at 5" = 5 pm
    # "at 3": the most recent 3 o'clock that has passed (3 pm in the evening, 3 am early in the morning).
    if hour == 12:
        return base if base <= now else base - datetime.timedelta(days=1)
    for c in (base + datetime.timedelta(hours=12), base):
        if c <= now:
            return c
    return base - datetime.timedelta(hours=12)


@action("timeline_at", "What the user was doing (which app, site, video or document) at a time in the past, e.g. "
        "'at 3 pm', 'an hour ago', 'yesterday at 5'.", "when: str")
def timeline_at(when=""):
    dt = past_time(when)
    if not dt:
        raise ActionError("What time? Say something like at 3 pm, or an hour ago.")
    if dt > datetime.datetime.now():
        raise ActionError("That hasn't happened yet.")
    ts = dt.timestamp()
    segs = _segments(ts - 1800, ts + 1800)
    inside = [s for s in segs if s["s"] - 5 <= ts <= s["e"] + 5]
    hit = max(inside, key=lambda s: s["e"] - s["s"]) if inside else None      # not a split-second alt-tab
    day = "" if _day_of(dt) == _day_of(datetime.datetime.now()) else " " + _day_name(_day_of(dt))
    if hit:
        block = next((b for b in _blocks(segs) if b["app"] == hit["app"] and b["s"] - 5 <= ts <= b["e"] + 5), hit)
        title = _title_at(hit, ts)
        what = "%s, with %s open" % (hit["app"], title) if title else hit["app"]
        return "At %s%s you were on %s, from %s to %s." % (_clock(ts), day, what, _clock(block["s"]),
                                                          _clock(block["e"]))
    before = [s for s in segs if s["e"] < ts]
    if before:
        b = before[-1]
        return "You were away from the PC at %s%s. Before that, until %s, you were on %s." % (
            _clock(ts), day, _clock(b["e"]), b["app"])
    return "I don't have anything for %s%s. I only know what happened while I was running, for the last two " \
           "weeks." % (_clock(ts), day)


def _match_app(segs, app):
    a = re.sub(r"^(?:the|my)\s+", "", (app or "").lower().strip())
    a = re.sub(r"\s+(?:app|game)$", "", a)
    hits = [s for s in segs if a and (a in s["app"].lower() or s["app"].lower() in a)]
    if not hits and len(a) > 2:
        hits = [s for s in segs if any(a in (x[1] or "").lower() for x in s.get("titles") or [])]
    return hits


@action("timeline_app", "When the user started, last used, or how long they've currently been on an app, game or "
        "site, from today's activity.", "app: str, which?: first|last|current, day?: today|yesterday")
def timeline_app(app="", which="first", day="today"):
    if not app:
        raise ActionError("Which app?")
    today = _day_of(datetime.datetime.now())
    d = today - datetime.timedelta(days=1 if day == "yesterday" else 0)
    start = _day_start(d)
    segs = _match_app(_segments(start, start + 86400), app)
    when = _day_name(d)
    if not segs:
        return "I didn't see you on %s %s." % (app, when)
    label = segs[0]["app"]
    name = label if app.lower() in label.lower() and len(label) < 25 else app[:1].upper() + app[1:]
    blocks = _blocks(segs)
    total = sum(s["e"] - s["s"] for s in segs)
    live = d == today and time.time() - blocks[-1]["e"] < GAP
    if which == "current" or (which == "first" and live and len(blocks) == 1):
        if live:
            return "You've been on %s since %s, %s so far." % (name, _clock(blocks[-1]["s"]),
                                                               duration_phrase(max(60, int(time.time() - blocks[-1]["s"]) // 60 * 60)))
        return "You're not on %s right now. You were on it until %s, %s." % (name, _clock(blocks[-1]["e"]),
                                                                           _ago(blocks[-1]["e"]))
    if which == "last":
        if live:
            return "You're on %s right now, since %s." % (name, _clock(blocks[-1]["s"]))
        return "You were last on %s%s at %s, %s." % (name, "" if when == "today" else " " + when,
                                                    _clock(blocks[-1]["e"]), _ago(blocks[-1]["e"]))
    first = "You started %s at %s%s" % (name, _clock(blocks[0]["s"]), "" if when == "today" else " " + when)
    if total >= 60:
        first += ", and spent %s on it in total" % duration_phrase(int(total) // 60 * 60)
    return first + (". You're still on it." if live else ".")


PARTS = {"morning": (5, 12), "afternoon": (12, 17), "evening": (17, 24), "night": (19, 29)}


@action("timeline_day", "The user's activity timeline: what they did and when, for today or yesterday, or part of "
        "the day.", "day?: today|yesterday, part?: morning|afternoon|evening|night")
def timeline_day(day="today", part=""):
    today = _day_of(datetime.datetime.now())
    d = today - datetime.timedelta(days=1 if day == "yesterday" else 0)
    midnight = datetime.datetime.combine(d, datetime.time()).timestamp()
    lo, hi = PARTS.get(part, (5, 29))
    blocks = [b for b in _blocks(_segments(midnight + lo * 3600, midnight + hi * 3600))
              if b["e"] - b["s"] >= 180 and b["e"] >= midnight + lo * 3600 and b["s"] <= midnight + hi * 3600]
    label = ("this " if d == today else _day_name(d) + " ") + part if part else _day_name(d)
    if part == "night":
        label = "last night" if d == today - datetime.timedelta(days=1) else "tonight"
    if not blocks:
        return "I don't have any activity for %s." % label
    rows = []
    for b in blocks[-12:]:
        title = _title_at(b, b["e"])
        rows.append({"icon": "dot", "text": "%s to %s · %s%s" % (_clock(b["s"]), _clock(b["e"]), b["app"],
                                                                 (" · " + title[:50]) if title else "")})
    spoken = ", then ".join("%s from %s" % (b["app"], _clock(b["s"])) for b in blocks[:4])
    if len(blocks) > 4:
        spoken += ", and %d more" % (len(blocks) - 4)
    return card("briefing", "%s: %s." % (label[:1].upper() + label[1:], spoken), greeting="Your timeline",
                rows=rows)
