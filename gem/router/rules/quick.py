"""Commands: Instant maths, conversions, stopwatch, clipboard and reading aloud."""
import re

from ...skills import calc
from ..core import Match


def register(rule):
    # Instant maths and conversions (no AI)
    @rule(r"\d|percent|\broot of\b")
    def _(m, t):
        return Match("calculate", {"expression": t}) if calc.calculate(t) else None

    @rule(r"\b(?:to|in|into|per)\b")
    def _(m, t):
        if not re.match(r"^(?:convert |how many |what(?:'s| is) |how much is |\d|a |an |one )", t):
            return None
        try:
            return Match("convert", {"query": t}) if calc.convert(t) else None
        except Exception:
            return Match("convert", {"query": t})

    # Stopwatch
    @rule(r"^(?:start|begin|resume) (?:a |the )?stopwatch$")
    def _(m, t):
        return Match("stopwatch", {"command": "start"})

    @rule(r"^(?:stop|pause|end) (?:the )?stopwatch$")
    def _(m, t):
        return Match("stopwatch", {"command": "stop"})

    @rule(r"^(?:reset|clear) (?:the )?stopwatch$")
    def _(m, t):
        return Match("stopwatch", {"command": "reset"})

    @rule(r"^(?:stopwatch|check (?:the )?stopwatch|what's the stopwatch at|how long on the stopwatch)$")
    def _(m, t):
        return Match("stopwatch", {"command": "status"})

    # Clipboard, reading aloud
    @rule(r"^(?:what did i copy|what have i copied|show (?:me )?my clipboard(?: history)?|(?:my )?clipboard history)$")
    def _(m, t):
        return Match("clipboard_history")

    @rule(r"^paste (?:what i copied|the thing i copied|my (?:last|previous) copy|the previous (?:thing|copy|clip)|"
          r"what i copied before|the one before|that again)$", safe=False)
    def _(m, t):
        return Match("clipboard_paste", {"number": 2}, False)

    @rule(r"^paste (?:clip |number |item )(\d+)$", safe=False)
    def _(m, t):
        return Match("clipboard_paste", {"number": int(m.group(1))}, False)

    @rule(r"^paste (?:the )?(?:thing|text|one|link|bit|what i copied) (?:about|with|that says|from|mentioning) (.+)$",
          safe=False)
    def _(m, t):
        return Match("clipboard_paste", {"match": m.group(1)}, False)

    @rule(r"^(?:clear|forget|delete) (?:my )?clipboard history$")
    def _(m, t):
        return Match("clipboard_clear")

    @rule(r"^read (?:this|that|it|the selection|the selected text)(?: (?:to me|out|aloud|out loud|for me))?$",
          safe=False)
    def _(m, t):
        return Match("read_aloud", {}, False)

    @rule(r"^read (?:my screen|the screen|what's on (?:my |the )?screen|this page|the page|this article|"
          r"this email|this document|the document|this post|these messages|the messages)(?: (?:to me|out|aloud|"
          r"out loud|for me))*$", safe=False)
    def _(m, t):
        return Match("read_screen", {}, False)

    @rule(r"^(?:keep reading|continue reading|read (?:the )?rest|read more|go on reading|carry on reading)$",
          safe=False)
    def _(m, t):
        return Match("read_more", {}, False)

    @rule(r"^copy (?:that|this|it|your (?:last )?answer|what you said|the answer)(?: to (?:my |the )?clipboard)?$")
    def _(m, t):
        return Match("copy_answer")
