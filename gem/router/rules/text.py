"""Commands: Text tools and dictation."""
from ..core import Match, _source, _THIS


def register(rule):
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

    @rule(r"^(?:fix (?:the )?(?:grammar|spelling)(?: (?:in|of) %s)?|proofread %s|correct %s)$" % (_THIS, _THIS, _THIS),
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
