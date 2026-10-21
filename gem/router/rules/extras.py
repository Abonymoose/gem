"""Commands: Wi-Fi, QR codes, short links, colours, app reminders and easter eggs."""
import re

from ..core import Match, said


def register(rule):
    # Little extras
    @rule(r"^(?:what's|what is|tell me|show me|give me|get me|copy) (?:the |my )?(?:wifi|wi-fi|wi fi) password"
          r"(?: for (.+))?$|^(?:wifi|wi-fi) password(?: for (.+))?$")
    def _(m, t):
        return Match("wifi_password", {"network": m.group(1) or m.group(2) or ""})

    @rule(r"^(?:make|create|show|give me|generate)(?: me)? (?:a |the )?(?:wifi|wi-fi|wi fi) (?:qr|qr code|code)"
          r"(?: for (?:guests|my friends|friends))?$|^(?:let|help) (?:my friends?|guests?|someone) (?:join|connect to) "
          r"(?:the |my )?(?:wifi|wi-fi)$|^(?:wifi|wi-fi) qr(?: code)?$")
    def _(m, t):
        return Match("wifi_qr")

    @rule(r"^(?:make|create|generate|give me)(?: me)? (?:a |an )?qr(?: code)?(?: for| of| from)? ?(.*)$|^qr code(?: for)? ?(.*)$")
    def _(m, t):
        what = (m.group(1) or m.group(2) or "").strip()
        if re.search(r"\b(?:wifi|wi-fi)\b", what):
            return Match("wifi_qr")
        raw = re.search(r"\bqr(?: code)?(?:\s+(?:for|of|from))?\s+(.+?)[.?!]*$", said(), re.I)   # keep URLs intact
        return Match("qr_code", {"text": raw.group(1) if raw else what})

    @rule(r"^(?:shorten|make (?:a )?short(?:er)? (?:link|url)(?: for)?)(?: this| that| the| my)?(?: link| url)?(?: .+)?$")
    def _(m, t):
        raw = re.search(r"https?://\S+", said())
        return Match("shorten_link", {"url": raw.group(0) if raw else ""})

    @rule(r"^(?:copy|grab|get|extract) (?:the |all the )?text (?:from|on|off|in) (?:my |the |this )?"
          r"(screen|image|picture|video|window|page|pdf)$|^copy (?:what's|whats) (?:written )?on (?:my |the )?screen$",
          safe=False)
    def _(m, t):
        return Match("copy_screen_text", {"what": "" if not m.group(1) or m.group(1) in ("screen", "window")
                                          else "the " + m.group(1)})

    @rule(r"^(?:what colou?r is (?:this|that|under (?:my|the) (?:mouse|cursor|pointer))|colou?r picker|pick (?:this|that) "
          r"colou?r|what(?:'s| is) (?:this|that) colou?r|copy (?:this|that) colou?r|(?:what's the )?hex (?:code )?(?:of|for) "
          r"(?:this|that)(?: colou?r)?)$")
    def _(m, t):
        return Match("color_picker")

    @rule(r"^(?:do a |do an )?(?:barrel roll|aileron roll)$|^do a (?:backflip|flip|spin|trick)$")
    def _(m, t):
        return Match("barrel_roll")

    @rule(r"^hello there$")
    def _(m, t):
        return Match("general_kenobi")
