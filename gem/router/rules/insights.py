"""Commands: Screen time, day recap, small helpers and reply mode."""
import re

from ...parse import parse_duration
from ...skills import replies
from ..core import Match


def register(rule):
    # Activity timeline
    @rule(r"^what (?:was i|were we|did i do|was i up to)(?: doing| working on| up to| on| watching| playing| "
          r"looking at)?(?: on (?:the|my) (?:pc|computer))? (.+)$")
    def _(m, t):
        from ...skills.timeline import past_time
        rest = m.group(1)
        part = re.search(r"\b(this|yesterday) (morning|afternoon|evening)\b|\b(last night)\b", rest)
        if past_time(rest):
            return Match("timeline_at", {"when": rest})
        if part:
            return Match("timeline_day", {"day": "yesterday" if "yesterday" in rest or part.group(3) else "today",
                                          "part": part.group(2) or "night"})
        if rest == "yesterday":
            return Match("timeline_day", {"day": "yesterday"})
        return None

    @rule(r"^(?:show (?:me )?|open |what's )?(?:my )?(?:activity )?timeline(?: (?:for )?(today|yesterday))?$")
    def _(m, t):
        return Match("timeline_day", {"day": m.group(1) or "today"})

    @rule(r"^when did i (?:first )?(?:start|open|begin|launch|get on|hop on|go on|boot up|load up|start playing|"
          r"start watching|start using) (.+?)( today| yesterday)?$")
    def _(m, t):
        return Match("timeline_app", {"app": m.group(1), "which": "first",
                                      "day": "yesterday" if m.group(2) == " yesterday" else "today"})

    @rule(r"^when (?:was i|did i) last (?:on|in|use|open|play|watch|using|playing|watching) (.+?)( today| yesterday)?$|"
          r"^when did i (?:stop|close|quit|get off|leave) (.+?)( today| yesterday)?$")
    def _(m, t):
        return Match("timeline_app", {"app": m.group(1) or m.group(3), "which": "last",
                                      "day": "yesterday" if (m.group(2) or m.group(4)) == " yesterday" else "today"})

    @rule(r"^how long have i been (?:playing|watching|using|in|on|working on|doing) (.+?)(?: for)?$")
    def _(m, t):
        if re.search(r"\b(?:today|this week)\b", t):
            return None                     # a total: screen time below
        return Match("timeline_app", {"app": m.group(1), "which": "current"})

    # Screen time and recap
    @rule(r"^(?:what(?:'s| is) |show (?:me )?|check )?(?:my )?screen ?time(?: today| for today)?$")
    def _(m, t):
        return Match("screen_time", {"period": "today"})

    @rule(r"^(?:what(?:'s| is) |show (?:me )?)?(?:my )?screen ?time (?:this|for the) week$")
    def _(m, t):
        return Match("screen_time", {"period": "week"})

    @rule(r"^how (?:long|much time) (?:have i|did i) (?:been on|spent on|spend on|used|use|played|play) (.+?)"
          r"(?: today| this week)?$")
    def _(m, t):
        return Match("screen_time", {"app": m.group(1), "period": "week" if "this week" in t else "today"})

    @rule(r"^(?:what did i do today|recap (?:my |the )?day|how was my day|day recap|summari[sz]e (?:my )?day|"
          r"what have i done today)$")
    def _(m, t):
        return Match("day_recap")

    # Little helpers
    @rule(r"^(?:generate|make|create|give me) (?:me )?(?:a )?(?:(?:strong|new|random|secure) )*password"
          r"(?: (?:with|of) (\d+) (?:characters|chars|letters))?$")
    def _(m, t):
        return Match("password", {"length": int(m.group(1) or 16)})

    @rule(r"^(?:pick|choose|decide)(?: one)?(?: between| from| for me between)? (.+ (?:or|and) .+)$|^should i (.+ or .+)$")
    def _(m, t):
        opts = [o.strip() for o in re.split(r",\s*|\s+or\s+|\s+and\s+", m.group(1) or m.group(2)) if o.strip()]
        return Match("choose", {"options": opts}) if len(opts) >= 2 else None

    @rule(r"^(?:what did i note about|find (?:my )?notes? (?:about|on)|search (?:my )?notes for|"
          r"do i have (?:a |any )?notes? (?:about|on)) (.+)$")
    def _(m, t):
        return Match("notes_search", {"query": m.group(1)})

    # Reply mode
    @rule(r"^(?:i'm |i am )?(?:going |stepping |heading )?(?:away|afk)(?: mode)?(?: for (.+)| until (.+))?$|"
          r"^(?:set |turn on )?away mode(?: for (.+)| until (.+))?$|^i'll be back (?:in (.+)|at (.+))$", safe=False)
    def _(m, t):
        g = m.groups()
        dur = g[0] or g[2] or g[4]
        until = g[1] or g[3] or g[5]
        secs = parse_duration(dur) if dur else None
        return Match("away_start", {"minutes": secs / 60.0} if secs else ({"until": until} if until else {}), False)

    @rule(r"^(?:tell (?:them|him|her|everyone|people) (?:that )?i'm away|say (?:that )?i'm away|"
          r"(?:send |type )?(?:my )?away (?:message|note)|reply (?:that )?i'm away)$", safe=False)
    def _(m, t):
        return Match("away_note", {}, False)

    @rule(r"^(?:make it|make that) (.+)$|^(try again|another one|redo it|rewrite it|different one|change it|"
          r"shorter|longer|more casual|more formal|funnier|nicer)$", safe=False)
    def _(m, t):
        if not replies.recent_draft():
            return None
        return Match("reply_revise", {"instruction": m.group(1) or m.group(2)}, False)

    @rule(r"^(?:reply to (?:this|that|them|him|her|it)|(?:draft|write) a (?:reply|response)(?: to (?:this|that|it))?|"
          r"reply for me|answer (?:this|that|them) for me)$", safe=False)
    def _(m, t):
        return Match("reply_draft", {}, False)
