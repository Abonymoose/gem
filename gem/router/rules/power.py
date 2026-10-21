"""Commands: Shut down or sleep when something finishes."""
from ...parse import parse_duration
from ..core import Match, _power_word


def register(rule):
    # Power when done
    @rule(r"^(turn off|shut down|shutdown|switch off|power off|sleep|go to sleep|hibernate|restart)"
          r"(?: the| my)?(?: pc| computer| laptop)? (?:when|after|once) (?:the |this |my )?"
          r"(movie|film|video|show|episode|music|song|playlist|stream|it|everything)(?: ends| is over| finishes| is done|"
          r" stops)?$|^(?:put the (?:pc|computer) to sleep|turn everything off) (?:when|after) (?:the |this )?"
          r"(?:movie|film|video|show)(?: ends| is over)?$", safe=False)
    def _(m, t):
        return Match("power_when", {"power": _power_word(m.group(1) or "sleep"), "trigger": "media_end"}, False)

    @rule(r"^(turn off|shut down|shutdown|switch off|power off|sleep|hibernate|restart)(?: the| my)?"
          r"(?: pc| computer| laptop)? (?:when|after|once) (?:my |the )?downloads? (?:finish(?:es)?|is done|are done|"
          r"completes?|ends?)$", safe=False)
    def _(m, t):
        return Match("power_when", {"power": _power_word(m.group(1)), "trigger": "download_done"}, False)

    @rule(r"^(turn off|shut down|shutdown|switch off|power off|sleep|hibernate|restart)(?: the| my)?"
          r"(?: pc| computer| laptop) in (.+)$", safe=False)
    def _(m, t):
        secs = parse_duration(m.group(2))
        return Match("power_when", {"power": _power_word(m.group(1)), "trigger": "time", "minutes": secs / 60.0},
                     False) if secs else None

    @rule(r"^(?:don't|dont|do not) (?:turn off|shut down|sleep|restart)(?: the)?(?: pc| computer)?$|"
          r"^cancel (?:the )?(?:sleep|power off|turn off)(?: plan| timer)?$")
    def _(m, t):
        return Match("power_when_cancel")
