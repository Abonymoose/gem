"""Commands: Pointing at things on screen and autofill."""
import re

from ..core import Match, said


def register(rule):
    # Pointing at things on screen (Gem outlines them; you click)
    @rule(r"^(?:where(?:'s| is| are) (?:the |my |this )?(.+?) on (?:my |the |this )?(?:screen|page|window)|"
          r"show me where (?:the |my )?(.+?) is|point (?:to|at|out) (?:the |my )?(.+)|highlight (?:the |my )?(.+)|"
          r"where do i (?:click|go|press|tap) (?:to |for )?(.+)|how do i (.+?) (?:here|on this page|in this app)|"
          r"where(?:'s| is) (?:the |my )?(.+? (?:button|link|tab|icon|menu|setting|settings|option|field|box|bar|"
          r"toggle|switch))(?: here)?)$", safe=False)
    def _(m, t):
        what = next(g for g in m.groups() if g)
        if re.search(r"\b(?:highlights?|outlines?|boxes)\b", what):
            return None
        return Match("explain_screen", {"question": said().strip() or t})

    @rule(r"^(?:spotlight|focus on|focus) (?:this|the|my) (?:window|app)$|^(?:turn on |start )?(?:the )?spotlight"
          r"(?: mode)?$|^dim everything (?:else|but this|except this(?: window)?)$|^help me focus(?: on this)?"
          r"(?: window)?$|^spotlight on$")
    def _(m, t):
        return Match("spotlight", {"on": True})

    @rule(r"^(?:turn off |stop |end |hide |close )(?:the )?spotlight(?: mode)?$|^spotlight off$|^stop dimming"
          r"(?: the screen)?$|^undim(?: the screen)?$")
    def _(m, t):
        return Match("spotlight", {"on": False})

    @rule(r"^(?:hide|clear|remove|get rid of) (?:the |those |that |these )?(?:highlights?|outlines?|boxes)$")
    def _(m, t):
        return Match("clear_highlights")

    # Autofill suggestions (shown and copied; you paste)
    @rule(r"^(?:auto ?fill|autocomplete|auto complete)(?: (?:this|it|that|the sheet|my sheet|the form|this page|"
          r"mode(?: on)?))?$|^(?:help me |can you )?fill (?:this|it|these|the blanks?|this sheet|the sheet|this form|"
          r"the form|this in|it in|in the blanks?|in this sheet|out this form)(?: in| out)?$|"
          r"^what (?:formula|function) (?:goes|should go|do i (?:use|need)|should i use)(?: here| in (?:this|that|the) "
          r"(?:cell|column|row|box)| for (.+))?$|^(?:give me|write|suggest|make) (?:a |the )?(?:formula|excel formula)"
          r"(?: for (.+)| here)?$|^(?:solve|answer|do|work out) (?:this|these|that|the|my)(?: (?:maths? |math )?"
          r"(?:question|questions|problem|problems|sum|sums|equation|equations|worksheet))?(?: for me)?$|"
          r"^what goes (?:here|in (?:this|that|the) (?:cell|box|blank|gap))$", safe=False)
    def _(m, t):
        return Match("autofill", {"request": said().strip() or t})

    @rule(r"^copy (?:the )?(first|second|third|fourth|last|1st|2nd|3rd|4th|next)(?: one| suggestion| answer| formula)?$|"
          r"^copy (?:number|no|suggestion|answer|formula) (\d)$")
    def _(m, t):
        from ...skills import autofill
        if not autofill.last["fills"]:
            return None
        word = m.group(1) or m.group(2)
        n = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "next": 0, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
             "last": -1}.get(word, int(word) if word and word.isdigit() else 1)
        return Match("autofill_copy", {"number": n})

    # Screen questions phrased loosely
    @rule(r"^(?:take a screenshot|screenshot (?:this|that|my screen)|look at (?:my |the |this )?screen|check (?:my |the )?"
          r"screen) and (.+)$", safe=False)
    def _(m, t):
        # "Take a screenshot and tell me X" is a question about the screen, not a request to save a picture.
        raw = re.search(r"\band\s+(.+?)[.?!]*$", said() or t, re.I)
        return Match("explain_screen", {"question": raw.group(1) if raw else m.group(1)})

    @rule(r"\bhighlight (?:the |my |what(?:'s| is) )?(.+?)(?: (?:on|in) (?:my|the) screen)?(?: right now| for me)?$",
          safe=False)
    def _(m, t):
        # "highlight ..." anywhere in the sentence, even after a misheard start ("I will highlight ...").
        if re.search(r"\b(?:highlights?|outlines?)\b", m.group(1)) or t.startswith(("hide", "clear", "remove")):
            return None
        return Match("explain_screen", {"question": said().strip() or t})