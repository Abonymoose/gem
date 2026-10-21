"""Commands: Time zones, countdowns and commands for later."""
import re

from ...parse import parse_duration
from ..core import Match, match, _routine


def register(rule):
    # Time zones and world clock
    @rule(r"^(?:convert |what(?:'s| is) )?(\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2}|noon|midnight) (?:in )?(.+?)"
          r"(?: time)? (?:in|to|into|for) (.+?)(?: time)?$")
    def _(m, t):
        return Match("time_convert", {"time": m.group(1), "from_place": m.group(2), "to_place": m.group(3)})

    @rule(r"^when it's (.+?) in (.+?) what time is it(?: (?:here|for me|in (.+)))?$")
    def _(m, t):
        return Match("time_convert", {"time": m.group(1), "from_place": m.group(2), "to_place": m.group(3) or "here"})

    @rule(r"^(?:what(?:'s| is) the )?(?:current )?time (?:in|at) (.+)$|^what time is it (?:in|at) (.+)$|"
          r"^how far (?:ahead|behind) is (.+)$|^what(?:'s| is) the time difference (?:with|to) (.+)$")
    def _(m, t):
        return Match("time_in", {"place": next(g for g in m.groups() if g)})

    @rule(r"^(?:show (?:me )?)?(?:my |the )?world clock$")
    def _(m, t):
        return Match("world_clock")

    @rule(r"^add (.+?) to (?:my |the )?world clock$")
    def _(m, t):
        return Match("world_clock", {"add": m.group(1)})

    @rule(r"^(?:remove|delete) (.+?) from (?:my |the )?world clock$")
    def _(m, t):
        return Match("world_clock", {"remove": m.group(1)})

    # Countdowns and saved dates
    @rule(r"^(?:how many (?:days|weeks|sleeps) (?:is it |are there |are left |left |do i have |until |till )?|"
          r"how long (?:is it |is left |do i have )?)(?:until|till|til|to|before|left until) (.+)$|"
          r"^(?:days|time) (?:until|till|left until|left till) (.+)$|^countdown to (.+)$|"
          r"^when(?:'s| is) (?:it )?(.+?)(?: this year| next year)?$")
    def _(m, t):
        to = next(g for g in m.groups() if g)
        if m.group(4):
            # "when is X" only for holidays and saved dates; "when is my next class" etc. go elsewhere.
            from ...skills import world
            key = re.sub(r"^(?:my|the)\s+", "", to)
            if key not in world.HOLIDAYS and (not to.startswith("my ") or
                                              re.search(r"\b(?:next|class|lesson|period|alarm|timer|reminder)\b", to)):
                return None
        return Match("countdown", {"to": to})

    @rule(r"^my ([a-z' ]{3,30}?) is (?:on )?(.+)$", safe=False)
    def _(m, t):
        from ...skills import world
        if len(m.group(1).split()) > 3 or not world.parse_date(m.group(2)):
            return None
        return Match("save_date", {"name": m.group(1), "date": m.group(2)}, False)

    # Scheduled commands
    @rule(r"^(?:set a |start a )?sleep timer(?: for)? (.+)$|^(?:pause|stop|turn off) (?:the )?music (?:in|after) (.+)$")
    def _(m, t):
        secs = parse_duration(m.group(1) or m.group(2))
        return Match("schedule_command", {"command": "pause everything", "minutes": secs / 60.0}) if secs else None

    @rule(r"^pause everything$")
    def _(m, t):
        return Match("media_pause")

    @rule(r"^(?:in|after) (\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)(?:\s*(?:and\s*)?\d+\s*"
          r"(?:minutes?|mins?))?),?\s+(?:then\s+)?(.+)$|^at (\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight),?\s+(.+)$",
          safe=False)
    def _(m, t):
        command = m.group(2) or m.group(4)
        if not command or command.startswith(("remind", "wake")) or not (match(command) or _routine(command)):
            return None
        if m.group(1):
            return Match("schedule_command", {"command": command, "minutes": parse_duration(m.group(1)) / 60.0}, False)
        return Match("schedule_command", {"command": command, "time": m.group(3)}, False)

    @rule(r"^(.+?),?\s+(?:in (\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?))|at (\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
          r"noon|midnight))$", safe=False)
    def _(m, t):
        command = m.group(1)
        if command.startswith(("remind", "wake", "set a", "set an", "alarm")) or not (match(command) or _routine(command)):
            return None
        if m.group(2):
            return Match("schedule_command", {"command": command, "minutes": parse_duration(m.group(2)) / 60.0}, False)
        return Match("schedule_command", {"command": command, "time": m.group(3)}, False)
