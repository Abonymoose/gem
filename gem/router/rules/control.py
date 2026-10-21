"""Commands: Quiet, resume, stop and listening modes."""
import re

from ...parse import parse_duration
from ..core import Match


def register(rule):
    # Quiet / resume / stop
    @rule(r"^(?:be quiet|quiet|shut up|stay quiet|stop talking|go quiet|go to sleep|sleep|mute yourself)\s+"
          r"(?:until i (?:say so|say|tell you|come back|am back|m back)|until i'm back|till i say(?: so)?|"
          r"indefinitely|for now|for the rest of the day)$")
    def _(m, t):
        return Match("quiet_until_resumed")

    @rule(r"^(?:shut up|be quiet|quiet|stay quiet|keep quiet|stop talking|silence|shush|hush|zip it|pipe down|"
          r"mute yourself|don't talk|go to sleep|sleep|take a break|give me (?:a )?(?:minute|moment|second))\b(.*)$")
    def _(m, t):
        rest = m.group(1).strip()
        # Only "quiet" + an optional length; "sleep timer 30 minutes" or "stop talking about X" are other things.
        if re.match(r"(?:timer|mode|tracker|schedule|about|on|with)\b", rest):
            return None
        secs = parse_duration(rest)
        if rest and not secs and rest not in ("for a bit", "for a while", "for a second", "for a moment", "for",
                                              "for now", "now", "already", "a bit"):
            return None
        return Match("snooze", {"minutes": secs / 60.0} if secs else {})

    @rule(r"\b(?:shut up|be quiet|stop talking|keep quiet|not talking to you)\b", safe=False)
    def _(m, t):
        # "Yadju, shut up, I'm not talking to you": quiet anywhere in the sentence (needs addressing).
        secs = parse_duration(t[m.end():])
        return Match("snooze", {"minutes": secs / 60.0} if secs else {}, False)

    @rule(r"^(?:i'm back|im back|speak up|you can talk(?: again)?|talk again|start talking|wake up|unsnooze|"
          r"unmute yourself|come back|you can speak(?: again)?)$")
    def _(m, t):
        return Match("resume")

    @rule(r"^(?:stop|cancel|never ?mind|forget it|that's all|that's it|nothing|enough|ok stop|okay stop)$")
    def _(m, t):
        return Match("stop")

    # Modes
    @rule(r"^(?:switch to |use |go to |enable |turn on |change to )?(push to talk|push-to-talk|always listening|"
          r"always on|always-listening)(?: mode)?$", safe=False)
    def _(m, t):
        return Match("set_mode", {"mode": "push_to_talk" if "push" in m.group(1) else "always_listening"}, False)

    @rule(r"^(?:switch|change|toggle) (?:listening |your )?modes?$", safe=False)
    def _(m, t):
        return Match("set_mode", {"mode": "toggle"}, False)

    @rule(r"^(?:start |begin |turn on |enable |enter |go into |activate )?(?:gaming|game) mode(?: on)?$|"
          r"^(?:let's game|lets game|time to game|"
          r"game time|gaming time)$", safe=False)
    def _(m, t):
        return Match("gaming_mode", {"on": True}, False)

    @rule(r"^(?:stop|exit|end|leave|disable|turn off|quit) (?:gaming|game)(?: mode)?$|^(?:gaming|game) mode off$")
    def _(m, t):
        return Match("gaming_mode", {"on": False})

    @rule(r"^(?:turn off|disable|mute|no more) (?:your )?voice(?: replies)?$|^(?:text only|captions only)(?: mode)?$",
          safe=False)
    def _(m, t):
        return Match("voice_replies", {"on": False}, False)

    @rule(r"^(?:turn on|enable|use) (?:your )?voice(?: replies)?$|^talk out loud$", safe=False)
    def _(m, t):
        return Match("voice_replies", {"on": True}, False)
