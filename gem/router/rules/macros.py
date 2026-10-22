"""Commands: Macros, and sending Discord / Google Chat messages and emails.

These come first: a message body ("... in 10 minutes", "turn the volume up") must never run as a command of its
own, and "stop recording" means the macro while one is being recorded.
"""
import re

from ..core import Match, said

# "Delete that macro": which one is for the AI to work out from the conversation, not a fuzzy name match.
_PRONOUNS = {"that", "this", "it", "the", "my", "last", "new", "same", "that one", "this one", "last one", "new one"}


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
        return Match("macro_record", {"command": "stop", "name": macros.clean_name(m.group(1) or "")}, False)

    @rule(r"^(?:cancel|discard|scrap|throw away|delete|forget)(?: the| that| this)? (?:macro )?recording$", safe=False)
    def _(m, t):
        from ...skills import macros
        return Match("macro_record", {"command": "cancel"}, False) if macros.recording() else None

    @rule(r"^(?:start |begin )?record(?:ing)? (?:a |me a |new |my )?macro(?: (?:called|named|for) (.+))?$|"
          r"^(?:watch|learn) (?:what i do|me)(?: and (?:call it|save it as|name it) (.+))?$|"
          r"^(?:start|begin) (?:a )?macro recording$", safe=False)
    def _(m, t):
        from ...skills import macros
        return Match("macro_record", {"command": "start", "name": macros.clean_name(m.group(1) or m.group(2) or "")},
                     False)

    @rule(r"^(call it|name it|save (?:it|that|this) as) (.+)$", safe=False)
    def _(m, t):
        from ...skills import macros
        name = m.group(2)
        if re.match(r"^(?:a )?(?:day|night|quits)$", name):
            return None
        explicit = bool(re.search(r"\bmacro\b", name))
        naming = m.group(1).startswith(("call", "name", "save it"))
        if not (explicit or (naming and (macros.awaiting_name() or macros.plan_recent()))):
            return None                         # "save this as ..." is screen memory otherwise
        return Match("macro_name", {"name": macros.clean_name(name)}, False)

    @rule(r"^(?:stop|cancel|abort|kill|end|halt)(?: the| this| my)? (?:macro|routine)$|"
          r"^stop (?:running|doing) (?:the macro|the routine|that|it)$")
    def _(m, t):
        from ...skills import macros
        return Match("macro_stop") if macros.running() else None     # nothing running: not worth a reply

    @rule(r"^(?:run|start|play|do)(?: the| my)? (.+?) (?:macro|routine)$|"
          r"^(?:run|play|start)(?: the| my)? (?:macro|routine) (?:called |named )?(.+)$", safe=False)
    def _(m, t):
        name = m.group(1) or m.group(2)
        if name in _PRONOUNS or re.search(r"\b(?:at|in|on|by|every|tomorrow|tonight)\b.*(?:\d|am|pm|morning|evening|"
                                          r"night|noon|midnight)$", name):
            return None                         # "run the macro called X at 7 pm": scheduling, not X now
        return Match("routine_run", {"name": name}, False)

    @rule(r"^(?:what (?:macros|routines) do i have|list (?:my )?macros|(?:show (?:me )?)?my macros)$", safe=False)
    def _(m, t):
        return Match("routine_list", {}, False)

    @rule(r"^(?:delete|remove)(?: the| my)? (.+?) (?:macro|routine)$|"
          r"^(?:delete|remove)(?: the| my)? (?:macro|routine) (?:called |named )?(.+)$", safe=False)
    def _(m, t):
        name = m.group(1) or m.group(2)
        return None if name in _PRONOUNS else Match("routine_delete", {"name": name}, False)

    @rule(r"^(?:figure out how to|work out how to|find a way to|automate|try to figure out how to) (.+)$", safe=False)
    def _(m, t):
        if not re.search(r"\b(?:open|click|type|press|install|set up|go to|turn (?:on|off)|switch|download|upload|"
                         r"sign (?:in|out)|log (?:in|out)|close|move|rename|copy|paste|save|sort|tidy|clean|"
                         r"organi[sz]e|launch|start|run|app|apps|window|tab|folder|file|files|browser|settings|"
                         r"desktop|pc|computer|discord|chrome|spotify|excel|word|notepad)\b", m.group(1)):
            return None                         # a question, not a task on the PC: the AI answers it
        raw = re.search(r"\b(?:how to|a way to|automate)\s+(.+?)[.?!]*$", said(), re.I)
        return Match("macro_auto", {"goal": raw.group(1) if raw else m.group(1)}, False)

    @rule(r"^[a-z]+(?: [a-z]+)? (?:is|goes by|is called|shows up as) .+ on (?:discord|google chat|g ?chat|hangouts)$",
          safe=False)
    def _(m, t):
        req = _messaging().parse_alias(said())
        return Match("contact_alias", req, False) if req else None

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
