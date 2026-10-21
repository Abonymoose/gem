"""Commands: Macros, and sending Discord / Google Chat messages and emails.

These come first: a message body ("... in 10 minutes", "turn the volume up") must never run as a command of its
own, and "stop recording" means the macro while one is being recorded.
"""
import re

from ..core import Match, said


def _messaging():
    from ...skills import messaging
    return messaging


def register(rule):
    @rule(r"^(?:(?:stop|end|finish|done|quit)(?: the)?(?: macro)? recording(?: the macro)?|stop the macro|"
          r"(?:save|finish) (?:it|the macro|the recording)|that's it|that's all|i'm done|im done|done)"
          r"(?:,? (?:and )?(?:call it|name it|save it as|as) (.+))?$", safe=False)
    def _(m, t):
        from ...skills import macros
        if not macros.recording():
            return None
        return Match("macro_record", {"command": "stop", "name": m.group(1) or ""}, False)

    @rule(r"^(?:cancel|discard|scrap|throw away|delete|forget)(?: the| that| this)? (?:macro )?recording$", safe=False)
    def _(m, t):
        from ...skills import macros
        return Match("macro_record", {"command": "cancel"}, False) if macros.recording() else None

    @rule(r"^(?:start |begin )?record(?:ing)? (?:a |me a |new |my )?macro(?: (?:called|named|for) (.+))?$|"
          r"^(?:watch|learn) (?:what i do|me)(?: and (?:call it|save it as|name it) (.+))?$|"
          r"^(?:start|begin) (?:a )?macro recording$", safe=False)
    def _(m, t):
        return Match("macro_record", {"command": "start", "name": m.group(1) or m.group(2) or ""}, False)

    @rule(r"^(?:call it|name it|save (?:it|that|this) as)(?: a| the)?(?: macro)?(?: called| named)? (.+)$", safe=False)
    def _(m, t):
        from ...skills import macros
        explicit = " macro" in t.split(" as ", 1)[-1] if " as " in t else False
        if not (macros.awaiting_name() or macros.plan_recent() or explicit):
            return None                         # "save this as ..." is screen memory otherwise
        return Match("macro_name", {"name": re.sub(r"\s+macro$", "", m.group(1))}, False)

    @rule(r"^(?:stop|cancel|abort|kill|end|halt)(?: the| this| my)? (?:macro|routine)$|"
          r"^stop (?:running|doing) (?:the macro|the routine|that|it)$")
    def _(m, t):
        return Match("macro_stop")

    @rule(r"^(?:run|start|play|do)(?: the| my)? (.+?) (?:macro|routine)$|"
          r"^(?:run|play|start)(?: the| my)? (?:macro|routine) (?:called |named )?(.+)$", safe=False)
    def _(m, t):
        return Match("routine_run", {"name": m.group(1) or m.group(2)}, False)

    @rule(r"^(?:what (?:macros|routines) do i have|list (?:my )?macros|(?:show (?:me )?)?my macros)$")
    def _(m, t):
        return Match("routine_list")

    @rule(r"^(?:delete|remove)(?: the| my)? (.+?) (?:macro|routine)$|"
          r"^(?:delete|remove)(?: the| my)? (?:macro|routine) (?:called |named )?(.+)$", safe=False)
    def _(m, t):
        return Match("routine_delete", {"name": m.group(1) or m.group(2)}, False)

    @rule(r"^(?:figure out how to|work out how to|find a way to|automate|try to figure out how to) (.+)$", safe=False)
    def _(m, t):
        raw = re.search(r"\b(?:how to|a way to|automate)\s+(.+?)[.?!]*$", said(), re.I)
        return Match("macro_auto", {"goal": raw.group(1) if raw else m.group(1)}, False)

    @rule(r"\b(?:discord|google chat|g ?chat|hangouts)\b", safe=False)
    def _(m, t):
        req = _messaging().parse_message(said())
        return Match("send_message", req, False) if req else None

    @rule(r"^(?:send |write )?(?:an? )?e-?mail\b", safe=False)
    def _(m, t):
        req = _messaging().parse_email(said())
        return Match("send_email", req, False) if req else None

    @rule(r"^(?:the )?[a-z]+(?: [a-z]+)?(?:'s| s) (?:e-?mail|discord|google chat|g ?chat)\b", safe=False)
    def _(m, t):
        req = _messaging().parse_contact(said())
        return Match("contact_save", req, False) if req else None
