"""Commands: Teaching Gem misheard words and correcting what it just heard."""
import re

from ..core import Match, said


def _as_said(words):
    """The words with the capitals you actually used ("Freya", not "freya")."""
    m = re.search(r"[\s,]+".join(map(re.escape, words.split())), said(), re.I)
    return m.group(0) if m else words


def register(rule):
    # "When I say free ya, I mean Freya"
    @rule(r"^(?:when|if|whenever) (?:i say|you hear) (.+?) (?:i mean|i'm saying|i am saying|i meant|it means|"
          r"that means|it's|its|it is|that's|say|write|hear it as|take it as) (.+)$", safe=False)
    def _(m, t):
        return Match("hearing_teach", {"heard": m.group(1), "meant": _as_said(m.group(2))})

    @rule(r"^you (?:keep hearing|always hear|keep writing|hear) (.+?) (?:but |when )?(?:i'm saying|i mean|it's|its|"
          r"it is|i said|i say|it should be) (.+)$", safe=False)
    def _(m, t):
        return Match("hearing_teach", {"heard": m.group(1), "meant": _as_said(m.group(2))})

    # "No, I said Spotify" / "I said Spotify, not spot if I"
    @rule(r"^(?:no |nope |nah |wait )?i said (.+?) not (.+)$", safe=False)
    def _(m, t):
        return Match("said_instead", {"said": _as_said(m.group(1)), "not_this": m.group(2)})

    @rule(r"^(?:no|nope|nah|wrong|not that) i (?:said|meant|asked for) (.+)$", safe=False)
    def _(m, t):
        return Match("said_instead", {"said": _as_said(m.group(1))})

    @rule(r"^(?:which|what) (?:ai|model|ai model|service) (?:are you|you're|is) (?:using|on|running)(?: right now)?$|"
          r"^(?:how much (?:ai|of your (?:ai|limit|allowance)) (?:have you|did you) used?(?: today)?|ai (?:status|usage))$")
    def _(m, t):
        return Match("ai_status")

    @rule(r"^(?:what|which) words (?:have i taught you|did i teach you|have you learned|did you learn)$|"
          r"^(?:list|show|read) (?:me )?(?:my |the |your )?(?:word|hearing) fixes$")
    def _(m, t):
        return Match("hearing_list")

    @rule(r"^(?:forget|remove|delete|clear) (?:all )?(?:the |my |your )?(?:word|hearing) fix(?:es)?(?: for (.+))?$|"
          r"^(?:forget|stop hearing) (.+?) as (?:.+)$", safe=False)
    def _(m, t):
        return Match("hearing_forget", {"heard": m.group(1) or m.group(2) or ""})
