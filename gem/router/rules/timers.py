"""Commands: Time, timers, alarms, reminders and the class schedule."""
import re

from ...config import runtime
from ...parse import parse_duration, parse_when, words_to_numbers
from ...skills import apps, timers
from ..core import Match, said


def _remembered_timer(label):
    """A timer label used before ('pasta'), so 'set a pasta timer' can reuse its length; else None."""
    label = re.sub(r"^(?:the|my|a|an)\s+", "", (label or "").strip())
    return label if label and label in (runtime.data.get("timer_lengths") or {}) else None


def register(rule):
    # Time and date
    @rule(r"^(?:what's the time|what is the time|what time is it|what's the time now|the time|time|"
          r"current time|tell me the time|time please|what time it is)(?: now| right now)?$")
    def _(m, t):
        return Match("clock", {"what": "time"})

    @rule(r"^(?:what's the date|what is the date|what's today's date|what is today's date|today's date|date|"
          r"what day is it|what day is today|what's today|what is today|which day is it)(?: today)?$")
    def _(m, t):
        return Match("clock", {"what": "date"})

    # Timers, alarms, reminders
    @rule(r"^(?:set |start |make |put on )?(?:an? )?(\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)"
          r"(?:\s*(?:and\s*)?\d+\s*(?:minutes?|mins?|seconds?|secs?))?)\s+timer(?:\s+(?:for|called|named)\s+(.+))?$")
    def _(m, t):
        return Match("set_timer", {"seconds": parse_duration(m.group(1)), "label": m.group(2) or ""})

    @rule(r"^(?:set |start |make )?(?:an? |the )?timer (?:for|of|to)\s+(.+?)(?:\s+(?:called|named|for)\s+(.+))?$")
    def _(m, t):
        secs = parse_duration(m.group(1))
        if not secs and not m.group(2) and _remembered_timer(m.group(1)):
            return Match("set_timer", {"label": m.group(1)})       # "set a timer for pasta", like last time
        return Match("set_timer", {"seconds": secs, "label": m.group(2) or ""}) if secs else None

    # Running timers: more time, less time, pause, resume
    @rule(r"^(?:add|put) (?:another |an extra |on )?(.+?) (?:more )?(?:to|on) (?:the |my |that )?(?:(.+?) )?timer$|"
          r"^take (.+?) off (?:the |my |that )?(?:(.+?) )?timer$")
    def _(m, t):
        secs = parse_duration(m.group(1) or m.group(3))
        if not secs:
            return None
        return Match("timer_adjust", {"seconds": secs if m.group(1) else -secs, "label": m.group(2) or m.group(4) or ""})

    @rule(r"\b(?:more|another|extra)\b", safe=False)
    def _(m, t):
        # "5 more minutes", "another minute", "add 2 more minutes": only while a timer is running.
        tn = re.sub(r"\b(?:another|an extra|one more)\s+(?=(?:minute|hour|second)\b)", "1 ", words_to_numbers(t))
        hit = re.fullmatch(r"(?:add |give (?:me|it) )?(?:another |an extra )?(\d+(?:\.\d+)?) (?:more |extra )?"
                           r"((?:minute|min|second|sec|hour)s?)(?: more)?(?: (?:on|to) (?:it|that|the timer))?", tn)
        if not hit or not timers._timer():
            return None
        return Match("timer_adjust", {"seconds": parse_duration(hit.group(1) + " " + hit.group(2))}, False)

    @rule(r"^(pause|stop|hold|freeze|resume|unpause|continue|restart) (?:the |my |that )?(?:(.+?) )?timer(?: again)?$|"
          r"^start (?:the |my )?(?:(.+?) )?timer again$")
    def _(m, t):
        verb, label = m.group(1), m.group(2) or m.group(3) or ""
        if verb == "stop" or (verb == "restart" and not timers._timer(label, "paused")):
            return None                                 # "stop the timer" cancels it (below)
        pause = verb in ("pause", "hold", "freeze")
        if not timers._timer(label, "running" if pause else "paused"):
            return None
        return Match("timer_pause", {"pause": pause, "label": label})

    @rule(r"^(set |start |make |put on )?(?:an? |the |my )?(.+?) timer$")
    def _(m, t):
        # "set a pasta timer" can be acted on when overheard; a bare "the pasta timer" needs Gem's name
        label = _remembered_timer(m.group(2))
        return Match("set_timer", {"label": label}, bool(m.group(1))) if label else None

    @rule(r"^how (?:much time|long) (?:is )?(?:left|remaining)(?: on (?:my |the )?(.+?) ?timer)?$|"
          r"^time left(?: on (?:my |the )?timer)?$")
    def _(m, t):
        if "focus" in t or "session" in t or "pomodoro" in t:
            return Match("focus_status")
        return Match("time_left", {"label": m.group(1) or ""})

    @rule(r"^(?:cancel|stop|delete|remove|clear|turn off|kill) (?:all )?(?:the |my |that )?(?:(.+?) )?"
          r"(timer|alarm|reminder)s?(?: (?:for|called|about|to) (.+))?$", safe=False)
    def _(m, t):
        name = m.group(1) or m.group(3) or ""
        if parse_duration(name) or name in ("all", "all the", "all my", "every", "both", "both the"):
            name = ""                                   # "the 10 minute timer": the one that's running
        return Match("cancel_timer", {"kind": m.group(2), "match": name,
                                      "all": bool(re.search(r"\b(?:all|every|both)\b", t))}, False)

    @rule(r"^(?:what are|list|show|read|tell me) (?:all )?(?:my |the )?(?:timers|alarms|reminders)$|"
          r"^do i have any (?:timers|alarms|reminders)$|^(?:my )?(?:timers|alarms|reminders)$")
    def _(m, t):
        return Match("list_timers")

    @rule(r"^snooze(?: (?:the |that |it|alarm|timer))*(?: for (.+))?$")
    def _(m, t):
        last = apps.svc.scheduler.last_fired if apps.svc.scheduler else None
        import time as _t
        if last and _t.time() - last[1] < 600:
            secs = parse_duration(m.group(1) or "")
            return Match("snooze_alarm", {"minutes": secs / 60.0} if secs else {})
        return Match("snooze")

    @rule(r"^(?:set |create |make )?(?:an? )?alarm (?:for|at)\s+(.+)$|^wake me(?: up)? (?:at|in)\s+(.+)$", safe=False)
    def _(m, t):
        when = m.group(1) or m.group(2)
        at, _ = parse_when(("in " if t.startswith("wake me up in") or t.startswith("wake me in") else "at ") + when)
        return Match("set_alarm", {"time": at.isoformat()}, False) if at else None

    @rule(r"^(?:remind me (?:to |about )?(.+?) (?:when|next time|the next time|once) i (?:open|start|launch|go on|get on) "
          r"(.+)|(?:when|next time|the next time) i (?:open|start|launch|go on|get on) (.+?),? remind me (?:to |about )?(.+))$",
          safe=False)
    def _(m, t):
        msg, app = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        # Same pattern on what you actually said, to keep names' capitals ("reply to Aarav").
        raw = re.search(m.re.pattern.replace("^", "").replace("$", ""), re.sub(r"[.!?]+$", "", said()), re.I)
        if raw:
            g = raw.groups()
            msg, app = (g[0], g[1]) if g[0] else (g[3], g[2])
        return Match("remind_on_open", {"app": app.strip(" ,"), "message": msg.strip(" ,")}, False)

    @rule(r"\bremind me\b", safe=False)
    def _(m, t):
        repeating = timers.parse_repeat(t)
        if repeating:
            msg, at, every = repeating
            return Match("set_reminder", {"message": msg, "time": at.isoformat() if at else None,
                                          "repeat_minutes": every}, False)
        parsed = timers.parse_reminder(t)
        if not parsed:
            return None
        msg, at = parsed
        return Match("set_reminder", {"message": msg, "time": at.isoformat()}, False)

    # Schedule
    @rule(r"^(?:what's|what is|what's on|tell me|read) (?:on )?my (?:schedule|classes|timetable)"
          r"(?: (?:for )?(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|this week))?$|"
          r"^(?:what|which) classes do i have(?: (today|tomorrow|on \w+))?$|"
          r"^do i have (?:any )?class(?:es)?(?: (today|tomorrow))?$")
    def _(m, t):
        day = next((g for g in m.groups() if g), "today").replace("on ", "")
        return Match("schedule_list", {"day": "week" if day == "this week" else day})

    @rule(r"^(?:when(?:'s| is) )?(?:my )?next class$|^when(?:'s| is) my next (?:class|lesson|event)$")
    def _(m, t):
        return Match("next_class")
