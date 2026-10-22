"""Commands: Voice lock and family voices."""
import re

from ..core import Match, said, _known_app, _RELATIONS, _NOT_NAMES


def register(rule):
    # Voice lock
    @rule(r"^(?:learn|train|memori[sz]e|recogni[sz]e|remember) (?:my voice|what i sound like|how i sound)$|"
          r"^(?:re)?train (?:my )?voice(?: recognition| lock)?$|^voice training$|"
          r"^set up (?:voice (?:recognition|lock|id)|my voice)$|^teach you my voice$", safe=False)
    def _(m, t):
        return Match("voice_train", {}, False)       # your voice approves big steps: never from overheard speech

    @rule(r"^(?:only (?:listen|respond|reply) to me|only (?:listen|respond) to my voice|listen only to me|"
          r"ignore (?:other|everyone else'?s?) (?:people|voices?)|ignore everyone else|"
          r"(?:turn on|enable) voice (?:lock|recognition|id)|voice (?:lock|recognition|id) on)$")
    def _(m, t):
        return Match("voice_lock", {"on": True})

    @rule(r"^(?:listen to (?:everyone|everybody|anyone)|respond to (?:everyone|everybody|anyone)|"
          r"(?:turn off|disable) voice (?:lock|recognition|id)|voice (?:lock|recognition|id) off)$")
    def _(m, t):
        return Match("voice_lock", {"on": False})

    @rule(r"^(?:do you know my voice|voice (?:check|status)|voice lock status|"
          r"how (?:sure|confident) are you (?:it'?s|that'?s|that it'?s) me|was that me|did that sound like me|"
          r"is voice lock on)$")
    def _(m, t):
        return Match("voice_status")

    @rule(r"^(?:forget|delete|reset|erase) my voice(?:print| profile)?$", safe=False)
    def _(m, t):
        return Match("voice_forget", {}, False)

    # Family voices
    @rule(r"^(?:learn|train|memori[sz]e|recogni[sz]e|remember) ((?:my |our )?[a-z' ]{2,30}?)(?:'s| s)? voice$")
    def _(m, t):
        who = m.group(1).strip()
        return None if who in ("my", "your", "this", "that", "a", "the") else Match("voice_train", {"person": who})

    @rule(r"^(?:that was|that's|that is|it was|this is) ((?:my |our )?(?:%s)(?: [a-z]+)?)(?: talking| speaking)?$"
          % "|".join(_RELATIONS), safe=False)
    def _(m, t):
        return Match("voice_label", {"person": m.group(1)}, False)

    @rule(r"^(?:that was|that's|that is|it was|this is) ([a-z]+)(?: talking| speaking| s voice|'s voice)?$", safe=False)
    def _(m, t):
        # "That was Freya": a known person, or a capitalised name in what Whisper wrote ("that was close" isn't).
        from ... import voiceprint
        name = m.group(1)
        proper = re.search(r"\b%s\b" % re.escape(name.capitalize()), said()) and name not in _NOT_NAMES
        return Match("voice_label", {"person": name}, False) if voiceprint.person(name) or proper else None

    @rule(r"^(?:block|ignore|stop listening to|don't listen to|dont listen to|stop responding to|"
          r"don't respond to|dont respond to) ((?:my |our )?[a-z' ]{2,30})$", safe=False)
    def _(m, t):
        who = m.group(1).strip()
        if who in _NOT_NAMES or _known_app(who) or who.split()[-1] in ("that", "this", "it", "them", "him", "her",
                                                                      "notifications", "ads", "calls", "messages"):
            return None
        return Match("voice_block", {"person": who, "on": True}, False)

    @rule(r"^(?:unblock|stop ignoring|you can listen to|you can respond to|listen to|respond to) "
          r"((?:my |our )?[a-z' ]{2,30})(?: again)?$", safe=False)
    def _(m, t):
        from ... import voiceprint
        from ...skills.voice_id import split_name
        who = m.group(1).strip()
        known = voiceprint.person(split_name(who)[0])
        if not known and not t.lower().startswith(("unblock", "stop ignoring")):
            return None                         # "listen to music" isn't about a person
        return Match("voice_block", {"person": who, "on": False}, False)

    @rule(r"^(?:who do you know|whose voices? do you know|who(?:'s| is) blocked|who have you blocked|"
          r"who(?:'s| is) on (?:the |my )?block ?list|(?:list|show) (?:the )?(?:people|voices|blocked people))$")
    def _(m, t):
        return Match("voice_people")
