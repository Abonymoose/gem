"""Commands: Text tools and dictation."""
import re

from ..core import Match, _source, _THIS, said


def register(rule):
    # Word count and spelling (both answered on the PC)
    @rule(r"^(?:how many (?:words|characters|letters)(?: are there| are| is)?(?: in)?|word count(?: of| for)?|"
          r"count (?:the )?words(?: in)?|how long is)(?: %s)?(?: (?:my|the) (?:essay|text|paragraph|document|story))?"
          r"(?: selection| essay| paragraph| text)?$|^(?:what's|what is) the (?:word|character) count(?: of %s)?$"
          % (_THIS, _THIS), safe=False)
    def _(m, t):
        # "how long is it" is usually about something else (a film, a wait), so it needs the text named
        if t.startswith("how long is") and not re.search(
                r"\b(?:this|that|selection|selected|essay|text|paragraph|document|story)\b", t):
            return None
        return Match("text_stats", {"source": _source(m.group(1) or m.group(2) or "")}, False)

    @rule(r"^(?:how (?:do|would|should) (?:you|i|we|one) spell|how (?:is|do you say|are you meant to write) (.+?) "
          r"(?:spelled|spelt)|spell(?: the word| out)?|(?:what's |what is )?the spelling of|spelling of)(?: (.*))?$",
          safe=False)
    def _(m, t):
        word = (m.group(1) or m.group(2) or "").strip()
        word = re.sub(r"^(?:the word|the name)\s+", "", word)
        if not word or len(word.split()) > 3 or word in ("it", "that", "this") or word.startswith("check") \
                or word.split()[0] in ("my", "your", "his", "her", "their"):
            return None                                 # "spell check this" is a grammar fix
        raw = re.search(re.escape(word).replace(r"\ ", r"[\s,]+"), said(), re.I)   # keep capitals: "Aarav"
        return Match("spell", {"word": raw.group(0) if raw else word}, False)

    # Text tools and dictation
    @rule(r"^(?:start |begin |turn on )?(?:dictation|dictating|dictate)(?: mode)?$|"
          r"^(?:type|write) (?:this|what i say)(?: down)?$|^take dictation$", safe=False)
    def _(m, t):
        return Match("dictation", {"on": True}, False)

    @rule(r"^summari[sz]e %s$" % _THIS, safe=False)
    def _(m, t):
        return Match("text_tool", {"task": "summarize", "source": _source(m.group(1))}, False)

    @rule(r"^explain %s$" % _THIS, safe=False)
    def _(m, t):
        return Match("text_tool", {"task": "explain", "source": _source(m.group(1))}, False)

    @rule(r"^(?:fix (?:the )?(?:grammar|spelling)(?: (?:in|of) %s)?|proofread %s|correct %s|spell ?check(?: %s)?)$"
          % (_THIS, _THIS, _THIS, _THIS),
          safe=False)
    def _(m, t):
        return Match("text_tool", {"task": "fix_grammar"}, False)

    @rule(r"^(?:make %s (?:shorter|more concise)|shorten %s)$" % (_THIS, _THIS), safe=False)
    def _(m, t):
        return Match("text_tool", {"task": "shorten"}, False)

    @rule(r"^translate %s(?: (?:in)?to (.+))?$" % _THIS, safe=False)
    def _(m, t):
        lang = m.group(2) or "English"
        return Match("text_tool", {"task": "translate", "instruction": "to " + lang,
                                   "source": _source(m.group(1))}, False)

    @rule(r"^(?:rewrite %s(?: (.+))?|make %s (?:sound )?(?:more )?(formal|professional|casual|friendly|polite|"
          r"clearer|simpler))$" % (_THIS, _THIS), safe=False)
    def _(m, t):
        style = m.group(2) or m.group(4) or ""
        return Match("text_tool", {"task": "rewrite", "instruction": style}, False)

    @rule(r"^(?:read (?:my |the )?clipboard|what's (?:on|in) (?:my |the )?clipboard)$")
    def _(m, t):
        return Match("read_clipboard")
