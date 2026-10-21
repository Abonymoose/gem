"""Commands: Explain my screen."""
from ..core import Match


def register(rule):
    # Explain my screen
    @rule(r"^(?:what(?:'s| is) (?:on )?(?:my|the|this) screen|what am i looking at|explain (?:my|the|this) screen|"
          r"(?:look at|read|check|scan) (?:my|the) screen|summari[sz]e (?:my|the|this) screen|"
          r"what(?:'s| is| does) this error(?: mean| say)?|what does (?:this|that) (?:error|message|pop ?up|warning) "
          r"(?:mean|say)|explain this (?:error|page|window|website|site|graph|chart|diagram|image|picture|problem|"
          r"question|meme|screen)|summari[sz]e this (?:page|website|site|article|window|post|thread)|"
          r"what(?:'s| is) this (?:error|page|website|site|game|app|window|meme)|how do i fix this(?: error)?)$")
    def _(m, t):
        return Match("explain_screen", {"question": t})

    @rule(r"^(?:look at|check|read) (?:my|the) screen,? (?:and )?(.+)$")
    def _(m, t):
        return Match("explain_screen", {"question": m.group(1)})
