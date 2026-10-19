"""Understanding numbers, durations and times in speech."""
import datetime
import re

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_WORD = r"(?:%s)" % "|".join(list(_UNITS) + list(_TENS) + ["hundred"])

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _words_values(words):
    """['twenty', 'five'] -> [25]; ['two', 'thirty'] -> [2, 30] (like a time)."""
    out, cur, have = [], 0, False
    for w in words:
        if w in _TENS:
            if have and cur % 100 != 0:      # "two thirty": a new number starts
                out.append(cur)
                cur = 0
            cur += _TENS[w]
        elif w in _UNITS:
            if have and cur % 10 != 0:       # "five five"
                out.append(cur)
                cur = 0
            cur += _UNITS[w]
        elif w == "hundred":
            cur = max(cur, 1) * 100
        have = True
    out.append(cur)
    return out


def words_to_numbers(text):
    """'twenty five minutes' -> '25 minutes', 'half an hour' -> '30 minutes'."""
    t = " " + text.lower() + " "
    t = re.sub(r"\bhalf an hour\b", "30 minutes", t)
    t = re.sub(r"\ban hour and a half\b", "90 minutes", t)
    t = re.sub(r"\b(?:a )?quarter of an hour\b", "15 minutes", t)
    t = re.sub(r"\ba couple(?: of)? (minute|hour|second)s?\b", r"2 \1s", t)
    t = re.sub(r"\ba few (minute|hour|second)s?\b", r"3 \1s", t)
    t = re.sub(r"\b(?:a|an) (minute|hour|second|day)\b", r"1 \1", t)
    t = re.sub(r"(\d+) and a half (hour|minute)s?", lambda m: "%g %ss" % (int(m.group(1)) + 0.5, m.group(2)), t)

    def repl(m):
        return " %s " % " ".join(str(v) for v in _words_values(re.split(r"[\s-]+", m.group(0))))

    t = re.sub(r"(?<![a-z])(?:%s)(?:[\s-]+%s)*(?![a-z])" % (_WORD, _WORD), repl, t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_time_words(text):
    t = text.lower()
    t = re.sub(r"\b([ap])\.\s?m\.?", r"\1m", t)
    t = re.sub(r"(\d)\s?([ap])m\b", r"\1 \2m", t)
    t = t.replace("o'clock", "").replace("oclock", "")
    return words_to_numbers(t)


_DUR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h\b|minutes?|mins?|m\b|seconds?|secs?|s\b)")


def parse_duration(text):
    """Seconds mentioned in text ('1 hour 20 minutes' -> 4800), or None."""
    t = words_to_numbers(text)
    total, found = 0.0, False
    for val, unit in _DUR_RE.findall(t):
        v = float(val)
        if unit.startswith("h"):
            total += v * 3600
        elif unit.startswith("m"):
            total += v * 60
        else:
            total += v
        found = True
    return int(total) if found and total > 0 else None


def duration_phrase(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append("%d hour%s" % (h, "" if h == 1 else "s"))
    if m:
        parts.append("%d minute%s" % (m, "" if m == 1 else "s"))
    if s and not h:
        parts.append("%d second%s" % (s, "" if s == 1 else "s"))
    return " and ".join(parts) if parts else "0 seconds"


def clock_phrase(dt, now=None):
    now = now or datetime.datetime.now()
    t = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == now.date():
        return t
    if dt.date() == (now + datetime.timedelta(days=1)).date():
        return t + " tomorrow"
    return t + " on " + dt.strftime("%A")


def parse_when(text, now=None):
    """Find a point in time in speech.

    Returns (datetime, matched_text) or (None, None). Understands "in 10
    minutes", "at 7", "at 6:30 pm", "tomorrow at 8 am", "on friday at noon",
    "19:55" and plain ISO timestamps.
    """
    now = now or datetime.datetime.now()
    raw = (text or "").strip()

    try:   # ISO from the model
        dt = datetime.datetime.fromisoformat(raw)
        return (dt.replace(tzinfo=None) if dt.tzinfo else dt), raw
    except ValueError:
        pass

    t = normalize_time_words(raw)

    m = re.search(r"\b(?:in|after)\s+((?:\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)\s*(?:and\s*)?)+)", t) \
        or re.search(r"((?:\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)\s*(?:and\s*)?)+)\s*from now", t)
    if m:
        secs = parse_duration(m.group(1))
        if secs:
            return now + datetime.timedelta(seconds=secs), m.group(0)

    day_offset, day_text = None, ""
    dm = re.search(r"\b(today|tonight|tomorrow|day after tomorrow)\b", t)
    if dm:
        day_offset = {"today": 0, "tonight": 0, "tomorrow": 1, "day after tomorrow": 2}[dm.group(1)]
        day_text = dm.group(0)
    else:
        wm = re.search(r"\b(?:on |next |this )?(%s)\b" % "|".join(WEEKDAYS), t)
        if wm:
            target = WEEKDAYS.index(wm.group(1))
            day_offset = (target - now.weekday()) % 7 or 7
            day_text = wm.group(0)

    hour = minute = None
    tm = re.search(r"\b(\d{1,2})(?::|\.)(\d{2})\s*(am|pm)?\b", t) \
        or re.search(r"\b(\d{1,2}) (\d{2})\s*(am|pm)\b", t) \
        or re.search(r"\b(\d{1,2})()\s*(am|pm)\b", t)
    if tm:
        hour, minute = int(tm.group(1)), int(tm.group(2) or 0)
        ampm = tm.group(3)
    elif re.search(r"\bnoon|midday\b", t):
        hour, minute, ampm, tm = 12, 0, None, re.search(r"\bnoon|midday\b", t)
    elif re.search(r"\bmidnight\b", t):
        hour, minute, ampm, tm = 0, 0, None, re.search(r"\bmidnight\b", t)
    else:
        tm = re.search(r"\b(?:at|for|by)\s+(\d{1,2})\b(?!\s*(?:minutes?|mins?|hours?|seconds?|percent|%))", t)
        if tm:
            hour, minute, ampm = int(tm.group(1)), 0, None
    if hour is None:
        return None, None
    if hour > 23 or minute > 59:
        return None, None

    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if dm and dm.group(1) == "tonight" and hour < 12:
        hour += 12

    base = now + datetime.timedelta(days=day_offset or 0)
    dt = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if ampm is None and hour <= 12 and day_offset is None:
        # "at 7" means the next 7 o'clock, morning or evening.
        candidates = [dt, dt + datetime.timedelta(hours=12), dt + datetime.timedelta(days=1)]
        if hour == 12:
            candidates = [dt, dt + datetime.timedelta(days=1)]
        dt = next(c for c in candidates if c > now)
    elif day_offset is None and dt <= now:
        dt += datetime.timedelta(days=1)
    matched = " ".join(x for x in (day_text, tm.group(0) if tm else "") if x)
    return dt, matched


def parse_percent(text):
    m = re.search(r"\b(\d{1,3})\s*(?:%|percent)?", words_to_numbers(text))
    if m:
        v = int(m.group(1))
        if 0 <= v <= 100:
            return v
    return None
