"""Commands: Time, timers, alarms, reminders and the class schedule."""
import re

from ...parse import parse_duration, parse_when
from ...skills import apps, timers
from ..core import Match, said


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
        return Match("set_timer", {"seconds": secs, "label": m.group(2) or ""}) if secs else None

    @rule(r"^how (?:much time|long) (?:is )?(?:left|remaining)(?: on (?:my |the )?(.+?) ?timer)?$|"
          r"^time left(?: on (?:my |the )?timer)?$")
    def _(m, t):
        if "focus" in t or "session" in t or "pomodoro" in t:
            return Match("focus_status")
        return Match("time_left", {"label": m.group(1) or ""})

    @rule(r"^(?:cancel|stop|delete|remove|clear|turn off) (?:all )?(?:the |my )?(timer|alarm|reminder)s?"
          r"(?: (?:for|called|about|to) (.+))?$", safe=False)
    def _(m, t):
        return Match("cancel_timer", {"kind": m.group(1), "match": m.group(2) or "",
                                      "all": " all " in " " + t + " "}, False)

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
