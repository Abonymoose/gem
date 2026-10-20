"""Instant, offline understanding of common commands.

Anything matched here runs without calling the AI, which makes it fast and
saves free-tier requests. Anything not matched goes to the AI planner.

safe=True marks commands that are harmless to run even if the speech wasn't
meant for Gem (always-listening mode); the rest need Gem's name, push-to-talk
or an ongoing conversation.
"""
import re
from dataclasses import dataclass, field

from .parse import parse_duration, parse_percent, parse_when, words_to_numbers
from .skills import apps, calc, habits, replies, timers


@dataclass
class Match:
    action: str
    args: dict = field(default_factory=dict)
    safe: bool = True


_NAME = r"(?:gem|jem)"


def normalize(text):
    """Lower-case, strip punctuation and politeness. Returns (text, said_gem)."""
    raw = text.strip()
    by_name = bool(re.search(r"\b%s\b" % _NAME, raw, re.I))
    t = raw.lower()
    t = re.sub(r"(?<=\d)[.:](?=\d)", ":", t)
    t = re.sub(r"\b([ap])\.m\.", r"\1m", t)
    trailing_name = bool(re.search(r",\s*%s[.!?]*$" % _NAME, t))
    t = re.sub(r"[^\w\s':%+-]", " ", t)
    t = re.sub(r"^(?:(?:hey|hi|ok|okay|yo|oi)\s+)?%s\b\s*" % _NAME, "", t.strip())
    if trailing_name:
        t = re.sub(r"\s*\b%s\s*$" % _NAME, "", t)
    for _ in range(2):
        t = re.sub(r"^(?:please|can you|could you|would you|will you|can u|i want you to|i need you to|"
                   r"go ahead and|just|quickly|now)\s+", "", t.strip())
        t = re.sub(r"\s+(?:please|for me|thanks|thank you|now|right now)$", "", t.strip())
    return re.sub(r"\s+", " ", t).strip(), by_name


# ── Helpers ──────────────────────────────────────────────────────────────────

_FOLDER_RE = r"^(?:my\s+)?(downloads|documents|desktop|pictures|music|videos)(?:\s+folder)?$"


def _openable(name):
    low = re.sub(r"^(?:the|my)\s+", "", name.lower().strip())
    low = re.sub(r"\s+(?:app|application|program)$", "", low)
    if apps.resolve_site(low) or re.match(_FOLDER_RE, name.lower().strip()):
        return True
    m = re.match(r"^(.+?)\s+settings$", low)
    if m and m.group(1) in apps.SETTINGS_PAGES:
        return True
    if low in (apps.svc.config.get("apps") or {}) or low in apps.BUILTIN_APPS:
        return True
    apps.index.ready.wait(timeout=3)
    entries = apps.index.entries
    return low in entries or any(k.startswith(low + " ") for k in entries)


def _known_app(name):
    low = name.lower().strip()
    procs = apps.svc.config.get("processes") or {}
    return low in procs or _openable(low)


def _source(word):
    if word and "clipboard" in word or word and "copied" in word:
        return "clipboard"
    return "auto"


_THIS = r"(this|that|it|the selection|the selected text|selected text|what i selected|my clipboard|" \
        r"the clipboard|what i copied|this text|that text)"


# ── Rules ────────────────────────────────────────────────────────────────────

def _rules():
    R = []

    def rule(pattern, safe=True):
        rx = re.compile(pattern)

        def deco(fn):
            R.append((rx, fn, safe))
            return fn
        return deco

    # Quiet / resume / stop
    @rule(r"^(?:be quiet|quiet|shut up|stay quiet|stop talking|go quiet|go to sleep|sleep|mute yourself)\s+"
          r"(?:until i (?:say so|say|tell you|come back|am back|m back)|until i'm back|till i say(?: so)?|"
          r"indefinitely|for now|for the rest of the day)$")
    def _(m, t):
        return Match("quiet_until_resumed")

    @rule(r"^(?:shut up|be quiet|quiet|stay quiet|keep quiet|stop talking|silence|shush|hush|zip it|pipe down|"
          r"mute yourself|don't talk|go to sleep|sleep|take a break|give me (?:a )?(?:minute|moment|second))\b(.*)$")
    def _(m, t):
        rest = m.group(1).strip()
        # Only "quiet" + an optional length; "sleep timer 30 minutes" or "stop talking about X" are other things.
        if re.match(r"(?:timer|mode|tracker|schedule|about|on|with)\b", rest):
            return None
        secs = parse_duration(rest)
        if rest and not secs and rest not in ("for a bit", "for a while", "for a second", "for a moment", "for",
                                              "for now", "now", "already", "a bit"):
            return None
        return Match("snooze", {"minutes": secs / 60.0} if secs else {})

    @rule(r"\b(?:shut up|be quiet|stop talking|keep quiet|not talking to you)\b", safe=False)
    def _(m, t):
        # "Yadju, shut up, I'm not talking to you": quiet anywhere in the sentence (needs addressing).
        secs = parse_duration(t[m.end():])
        return Match("snooze", {"minutes": secs / 60.0} if secs else {}, False)

    @rule(r"^(?:i'm back|im back|speak up|you can talk(?: again)?|talk again|start talking|wake up|unsnooze|"
          r"unmute yourself|come back|you can speak(?: again)?)$")
    def _(m, t):
        return Match("resume")

    @rule(r"^(?:stop|cancel|never ?mind|forget it|that's all|that's it|nothing|enough|ok stop|okay stop)$")
    def _(m, t):
        return Match("stop")

    # Modes
    @rule(r"^(?:switch to |use |go to |enable |turn on |change to )?(push to talk|push-to-talk|always listening|"
          r"always on|always-listening)(?: mode)?$", safe=False)
    def _(m, t):
        return Match("set_mode", {"mode": "push_to_talk" if "push" in m.group(1) else "always_listening"}, False)

    @rule(r"^(?:switch|change|toggle) (?:listening |your )?modes?$", safe=False)
    def _(m, t):
        return Match("set_mode", {"mode": "toggle"}, False)

    @rule(r"^(?:start |begin |turn on |enable |enter |go into |activate )?(?:gaming|game) mode(?: on)?$|"
          r"^(?:let's game|lets game|time to game|"
          r"game time|gaming time)$", safe=False)
    def _(m, t):
        return Match("gaming_mode", {"on": True}, False)

    @rule(r"^(?:stop|exit|end|leave|disable|turn off|quit) (?:gaming|game)(?: mode)?$|^(?:gaming|game) mode off$")
    def _(m, t):
        return Match("gaming_mode", {"on": False})

    @rule(r"^(?:turn off|disable|mute|no more) (?:your )?voice(?: replies)?$|^(?:text only|captions only)(?: mode)?$",
          safe=False)
    def _(m, t):
        return Match("voice_replies", {"on": False}, False)

    @rule(r"^(?:turn on|enable|use) (?:your )?voice(?: replies)?$|^talk out loud$", safe=False)
    def _(m, t):
        return Match("voice_replies", {"on": True}, False)

    # Instant maths and conversions (no AI)
    @rule(r"\d|percent|square root")
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

    @rule(r"^copy (?:that|this|it|your (?:last )?answer|what you said|the answer)(?: to (?:my |the )?clipboard)?$")
    def _(m, t):
        return Match("copy_answer")

    # Time zones and world clock
    @rule(r"^(?:convert |what(?:'s| is) )?(\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2}|noon|midnight) (?:in )?(.+?)"
          r"(?: time)? (?:in|to|into|for) (.+?)(?: time)?$")
    def _(m, t):
        return Match("time_convert", {"time": m.group(1), "from_place": m.group(2), "to_place": m.group(3)})

    @rule(r"^when it's (.+?) in (.+?) what time is it(?: (?:here|for me|in (.+)))?$")
    def _(m, t):
        return Match("time_convert", {"time": m.group(1), "from_place": m.group(2), "to_place": m.group(3) or "here"})

    @rule(r"^(?:what(?:'s| is) the )?(?:current )?time (?:in|at) (.+)$|^what time is it (?:in|at) (.+)$|"
          r"^how far (?:ahead|behind) is (.+)$|^what(?:'s| is) the time difference (?:with|to) (.+)$")
    def _(m, t):
        return Match("time_in", {"place": next(g for g in m.groups() if g)})

    @rule(r"^(?:show (?:me )?)?(?:my |the )?world clock$")
    def _(m, t):
        return Match("world_clock")

    @rule(r"^add (.+?) to (?:my |the )?world clock$")
    def _(m, t):
        return Match("world_clock", {"add": m.group(1)})

    @rule(r"^(?:remove|delete) (.+?) from (?:my |the )?world clock$")
    def _(m, t):
        return Match("world_clock", {"remove": m.group(1)})

    # Countdowns and saved dates
    @rule(r"^(?:how many (?:days|weeks|sleeps) |how long )(?:until|till|til|to|before|left until) (.+)$|"
          r"^(?:days|time) (?:until|till|left until|left till) (.+)$|^countdown to (.+)$|"
          r"^when(?:'s| is) (?:it )?(.+?)(?: this year| next year)?$")
    def _(m, t):
        to = next(g for g in m.groups() if g)
        if m.group(4):
            # "when is X" only for holidays and saved dates; "when is my next class" etc. go elsewhere.
            from .skills import world
            key = re.sub(r"^(?:my|the)\s+", "", to)
            if key not in world.HOLIDAYS and (not to.startswith("my ") or
                                              re.search(r"\b(?:next|class|lesson|period|alarm|timer|reminder)\b", to)):
                return None
        return Match("countdown", {"to": to})

    @rule(r"^my ([a-z' ]{3,30}?) is (?:on )?(.+)$", safe=False)
    def _(m, t):
        from .skills import world
        if len(m.group(1).split()) > 3 or not world.parse_date(m.group(2)):
            return None
        return Match("save_date", {"name": m.group(1), "date": m.group(2)}, False)

    # Scheduled commands
    @rule(r"^(?:set a |start a )?sleep timer(?: for)? (.+)$|^(?:pause|stop|turn off) (?:the )?music (?:in|after) (.+)$")
    def _(m, t):
        secs = parse_duration(m.group(1) or m.group(2))
        return Match("schedule_command", {"command": "pause everything", "minutes": secs / 60.0}) if secs else None

    @rule(r"^pause everything$")
    def _(m, t):
        return Match("media_pause")

    @rule(r"^(?:in|after) (\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)(?:\s*(?:and\s*)?\d+\s*"
          r"(?:minutes?|mins?))?),?\s+(?:then\s+)?(.+)$|^at (\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight),?\s+(.+)$",
          safe=False)
    def _(m, t):
        command = m.group(2) or m.group(4)
        if not command or command.startswith(("remind", "wake")) or not (match(command) or _routine(command)):
            return None
        if m.group(1):
            return Match("schedule_command", {"command": command, "minutes": parse_duration(m.group(1)) / 60.0}, False)
        return Match("schedule_command", {"command": command, "time": m.group(3)}, False)

    @rule(r"^(.+?),?\s+(?:in (\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?))|at (\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
          r"noon|midnight))$", safe=False)
    def _(m, t):
        command = m.group(1)
        if command.startswith(("remind", "wake", "set a", "set an", "alarm")) or not (match(command) or _routine(command)):
            return None
        if m.group(2):
            return Match("schedule_command", {"command": command, "minutes": parse_duration(m.group(2)) / 60.0}, False)
        return Match("schedule_command", {"command": command, "time": m.group(3)}, False)

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

    # Time and date
    @rule(r"^(?:what's the time|what is the time|what time is it|what's the time now|the time|time|"
          r"current time|tell me the time|time please|what time it is)(?: now| right now)?$")
    def _(m, t):
        return Match("clock", {"what": "time"})

    @rule(r"^(?:what's the date|what is the date|what's today's date|what is today's date|today's date|date|"
          r"what day is it|what day is today|what's today|what is today|which day is it)(?: today)?$")
    def _(m, t):
        return Match("clock", {"what": "date"})

    # Timers, alarms, reminders
    @rule(r"^(?:set |start |make |put on )?(?:an? )?(\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)"
          r"(?:\s*(?:and\s*)?\d+\s*(?:minutes?|mins?|seconds?|secs?))?)\s+timer(?:\s+(?:for|called|named)\s+(.+))?$")
    def _(m, t):
        return Match("set_timer", {"seconds": parse_duration(m.group(1)), "label": m.group(2) or ""})

    @rule(r"^(?:set |start |make )?(?:an? |the )?timer (?:for|of|to)\s+(.+?)(?:\s+(?:called|named|for)\s+(.+))?$")
    def _(m, t):
        secs = parse_duration(m.group(1))
        return Match("set_timer", {"seconds": secs, "label": m.group(2) or ""}) if secs else None

    @rule(r"^how (?:much time|long) (?:is )?(?:left|remaining)(?: on (?:my |the )?(.+?) ?timer)?$|"
          r"^time left(?: on (?:my |the )?timer)?$")
    def _(m, t):
        if "focus" in t or "session" in t or "pomodoro" in t:
            return Match("focus_status")
        return Match("time_left", {"label": m.group(1) or ""})

    @rule(r"^(?:cancel|stop|delete|remove|clear|turn off) (?:all )?(?:the |my )?(timer|alarm|reminder)s?"
          r"(?: (?:for|called|about|to) (.+))?$", safe=False)
    def _(m, t):
        return Match("cancel_timer", {"kind": m.group(1), "match": m.group(2) or "",
                                      "all": " all " in " " + t + " "}, False)

    @rule(r"^(?:what are|list|show|read|tell me) (?:all )?(?:my |the )?(?:timers|alarms|reminders)$|"
          r"^do i have any (?:timers|alarms|reminders)$|^(?:my )?(?:timers|alarms|reminders)$")
    def _(m, t):
        return Match("list_timers")

    @rule(r"^snooze(?: (?:the |that |it|alarm|timer))*(?: for (.+))?$")
    def _(m, t):
        last = apps.svc.scheduler.last_fired if apps.svc.scheduler else None
        import time as _t
        if last and _t.time() - last[1] < 600:
            secs = parse_duration(m.group(1) or "")
            return Match("snooze_alarm", {"minutes": secs / 60.0} if secs else {})
        return Match("snooze")

    @rule(r"^(?:set |create |make )?(?:an? )?alarm (?:for|at)\s+(.+)$|^wake me(?: up)? (?:at|in)\s+(.+)$", safe=False)
    def _(m, t):
        when = m.group(1) or m.group(2)
        at, _ = parse_when(("in " if t.startswith("wake me up in") or t.startswith("wake me in") else "at ") + when)
        return Match("set_alarm", {"time": at.isoformat()}, False) if at else None

    @rule(r"\bremind me\b", safe=False)
    def _(m, t):
        parsed = timers.parse_reminder(t)
        if not parsed:
            return None
        msg, at = parsed
        return Match("set_reminder", {"message": msg, "time": at.isoformat()}, False)

    # Schedule
    @rule(r"^(?:what's|what is|what's on|tell me|read) (?:on )?my (?:schedule|classes|timetable)"
          r"(?: (?:for )?(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|this week))?$|"
          r"^(?:what|which) classes do i have(?: (today|tomorrow|on \w+))?$|"
          r"^do i have (?:any )?class(?:es)?(?: (today|tomorrow))?$")
    def _(m, t):
        day = next((g for g in m.groups() if g), "today").replace("on ", "")
        return Match("schedule_list", {"day": "week" if day == "this week" else day})

    @rule(r"^(?:when(?:'s| is) )?(?:my )?next class$|^when(?:'s| is) my next (?:class|lesson|event)$")
    def _(m, t):
        return Match("next_class")

    # To-do and notes
    @rule(r"^(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my |the )?(?:to ?do|to-do|todo|task|tasks|shopping)?\s*list$",
          safe=False)
    def _(m, t):
        # Commas are gone from the normalized text, so split on the raw words.
        raw = re.search(r"(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my |the )?[\w -]*list", _raw.lower())
        chunk = raw.group(1) if raw else m.group(1)
        if "," in chunk:
            items = re.split(r",\s*(?:and\s+)?|\s+and\s+", chunk)
        else:
            items = [chunk]
        items = [re.sub(r"[^\w\s'-]", "", i).strip() for i in items]
        return Match("todo_add", {"items": [i for i in items if i]}, False)

    @rule(r"^(?:what's|what is|read|show me|tell me|check) (?:on )?(?:my |the )?(?:to ?do|to-do|todo|task)s?"
          r"(?: list)?$|^what do i (?:have|need) to do(?: today)?$|^(?:my )?(?:to ?do|to-do|todo) list$")
    def _(m, t):
        return Match("todo_list")

    @rule(r"^(?:mark|check off|cross off|tick off|complete|finish|i finished|i did|i've done|done with)\s+(.+?)"
          r"(?:\s+(?:as )?(?:done|complete|completed|off))?(?:\s+(?:on|from) (?:my |the )?(?:to ?do |to-do |todo )?list)?$",
          safe=False)
    def _(m, t):
        return Match("todo_done", {"item": m.group(1)}, False)

    @rule(r"^(?:remove|delete|take)\s+(.+?)\s+(?:from|off)\s+(?:my |the )?(?:to ?do |to-do |todo )?list$", safe=False)
    def _(m, t):
        return Match("todo_remove", {"item": m.group(1)}, False)

    @rule(r"^(?:take a note|make a note|note|write down|jot down|note down|add a note)\s+(?:that\s+)?(.+)$", safe=False)
    def _(m, t):
        return Match("note_add", {"text": m.group(1)}, False)

    @rule(r"^(?:read|what are|tell me) (?:my |the )?(?:latest |last )?notes$")
    def _(m, t):
        return Match("notes_read")

    @rule(r"^(?:open|show) (?:my |the )?notes$")
    def _(m, t):
        return Match("notes_open")

    # Memory
    @rule(r"^what do you (?:remember|know) about me$|^what have i told you to remember$")
    def _(m, t):
        return Match("memories")

    @rule(r"^remember (?:that )?(.+)$", safe=False)
    def _(m, t):
        if m.group(1).startswith("to "):      # "remember to call mom" is a task; let the AI decide
            return None
        return Match("remember", {"fact": m.group(1)}, False)

    @rule(r"^forget (?:that |about )?(.+)$", safe=False)
    def _(m, t):
        return Match("forget", {"about": m.group(1)}, False)

    # Focus and briefing
    @rule(r"^(?:start |begin )?(?:a )?(?:focus|pomodoro|study|deep work)(?: session| mode| timer)?"
          r"(?: for (.+))?$", safe=False)
    def _(m, t):
        secs = parse_duration(m.group(1) or "")
        return Match("focus_start", {"minutes": secs / 60.0} if secs else {}, False)

    @rule(r"^(?:stop|end|cancel|finish) (?:the |my )?(?:focus|pomodoro|study)(?: session| mode)?$")
    def _(m, t):
        return Match("focus_stop")

    @rule(r"^(?:good morning|morning briefing|daily briefing|brief me|give me (?:my|a|the) briefing|"
          r"what's my day(?: look like)?|what does my day look like|catch me up)$", safe=False)
    def _(m, t):
        return Match("briefing", {}, False)

    # Weather
    @rule(r"^(?:my city is|i live in|set my city to|my home city is|set my location to)\s+(.+)$", safe=False)
    def _(m, t):
        return Match("set_home_city", {"city": m.group(1)}, False)

    @rule(r"^(?:what's |what is |how's |how is )?(?:the )?(?:weather|forecast|temperature)(?: like)?"
          r"(?: (?:in|for|at) (.+?))?(?: (today|tomorrow|now|right now|outside))?$")
    def _(m, t):
        when = {"today": "today", "tomorrow": "tomorrow"}.get(m.group(2) or "", "now")
        if "forecast" in t and when == "now":
            when = "today"
        return Match("weather", {"city": m.group(1), "when": when})

    @rule(r"^(?:is it|will it|is it going to|is it gonna) (?:rain|snow|be cold|be hot)(?: (?:in (.+?)))?"
          r"(?: (today|tomorrow|tonight))?$")
    def _(m, t):
        return Match("weather", {"city": m.group(1), "when": "tomorrow" if m.group(2) == "tomorrow" else "today"})

    # Gaming and PC
    @rule(r"^(?:(?:un)?mute|(?:un)?deafen) (?:me|myself|my mic(?:rophone)?)(?: (?:on|in) discord)?$|"
          r"^(?:(?:un)?mute|(?:un)?deafen) (?:me |myself )?(?:on|in) discord$|^discord (?:un)?(?:mute|deafen)$|"
          r"^toggle (?:discord )?(?:mute|deafen)$", safe=False)
    def _(m, t):
        return Match("discord_toggle", {"what": "deafen" if "deaf" in m.group(0) else "mute"}, False)

    @rule(r"^(?:clip (?:that|it|this)|clip the last (?:\d+ |thirty |30 )?seconds?|save (?:that|a|the) clip|"
          r"save the last (?:\d+ |thirty )?seconds|record (?:that|what just happened))(?: please)?$")
    def _(m, t):
        return Match("clip_that")

    @rule(r"^(?:run an? |do an? |start an? )?(?:internet |wifi |wi-fi |network )?speed ?test$|"
          r"^(?:how fast is|what's the speed of|check the speed of|test the speed of) (?:my |the )?"
          r"(?:internet|wifi|wi-fi|connection|network)(?: right now)?$|"
          r"^(?:my )?(?:internet|wifi|wi-fi|network|download) speed$|^test (?:my )?(?:internet|wifi|wi-fi) speed$")
    def _(m, t):
        return Match("speed_test")

    @rule(r"^(?:clean|clean up|tidy|tidy up|organi[sz]e|sort|sort out) (?:my |the )?downloads(?: folder)?$")
    def _(m, t):
        return Match("tidy_downloads")

    @rule(r"^(?:undo (?:the |that )?(?:tidy|tidy up|cleanup|clean up|organi[sz]ing)|put my downloads back|"
          r"undo (?:the )?downloads (?:tidy|cleanup))$")
    def _(m, t):
        return Match("tidy_undo")

    @rule(r"^(?:what should i|what can i|what do i|give me something to|recommend (?:me )?something to|"
          r"suggest something to|find me something to|i want something to) (watch|play)"
          r"(?: (?:tonight|today|now|later))?(?:,? (?:something )?(.+?))?$")
    def _(m, t):
        return Match("picks", {"kind": m.group(1), "mood": m.group(2) or ""})

    @rule(r"^(?:recommend|suggest)(?: me)? (?:a |an |some )?((?:[a-z-]+ ){0,2})"
          r"(movies?|shows?|series|anime|games?|youtube videos?|youtubers?)(?: to (?:watch|play))?"
          r"(?: (?:tonight|today))?$")
    def _(m, t):
        what = m.group(2)
        return Match("picks", {"kind": "play" if what.startswith("game") else "watch",
                               "mood": (m.group(1) + what).strip()})

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

    # Volume
    @rule(r"^(?:what's|what is|check) (?:the |my )?volume(?: level)?$|^how loud is it$|^volume level$")
    def _(m, t):
        return Match("volume")

    @rule(r"^(mute|unmute)(?: the)?(?: (?:sound|volume|audio|pc|computer|everything|speakers))?$", safe=False)
    def _(m, t):
        return Match("volume", {"mute": m.group(1) == "mute"}, False)

    @rule(r"^(mute|unmute)\s+(.+)$", safe=False)
    def _(m, t):
        return Match("volume", {"mute": m.group(1) == "mute", "app": m.group(2)}, False) \
            if _known_app(m.group(2)) else None

    @rule(r"^(?:max|maximum|full) volume$|^volume (?:max|maximum|full)$|^(?:turn it|volume) all the way up$")
    def _(m, t):
        return Match("volume", {"level": 100})

    @rule(r"volume")
    def _(m, t):
        tn = words_to_numbers(t)
        app = None
        am = re.search(r"(?:set |change |turn )?(?:the )?(.+?)(?:'s)? volume", tn)
        if am and am.group(1) not in ("the", "my", "set", "change", "turn", "set the", "your") and _known_app(am.group(1)):
            app = am.group(1)
        if re.search(r"\b(?:up|increase|raise|louder|higher|boost)\b", tn):
            n = re.search(r"\bby (\d+)", tn)
            return Match("volume", {"change": int(n.group(1)) if n else 10, "app": app})
        if re.search(r"\b(?:down|decrease|lower|reduce|quieter)\b", tn):
            n = re.search(r"\bby (\d+)", tn)
            return Match("volume", {"change": -(int(n.group(1)) if n else 10), "app": app})
        pct = parse_percent(tn)
        if pct is not None:
            return Match("volume", {"level": pct, "app": app})
        return None

    @rule(r"^(?:louder|turn it up|turn up the sound|turn the sound up)$")
    def _(m, t):
        return Match("volume", {"change": 10})

    @rule(r"^(?:quieter|softer|turn it down|turn down the sound|turn the sound down)$")
    def _(m, t):
        return Match("volume", {"change": -10})

    @rule(r"^(?:turn|lower|raise) (?:down |up )?(.+?)(?: (down|up))?$")
    def _(m, t):
        name = re.sub(r"^(?:down|up)\s+", "", m.group(1))
        if not _known_app(name) or not re.search(r"\b(?:down|up|lower|raise)\b", t):
            return None
        up = " up" in " " + t or t.startswith("raise")
        return Match("volume", {"change": 15 if up else -15, "app": name})

    # Media
    @rule(r"^(?:pause|play|resume|unpause)(?: the)?(?: music| song| track| video| it| spotify| that)?$")
    def _(m, t):
        return Match("media", {"command": "play_pause"})

    @rule(r"^(?:next|skip)(?: this)?(?: song| track| one| video)?$|^play (?:the )?next (?:song|track)$")
    def _(m, t):
        return Match("media", {"command": "next"})

    @rule(r"^(?:previous|go back|last)(?: a)?(?: song| track)$|^previous$|^play (?:the )?(?:previous|last) (?:song|track)$")
    def _(m, t):
        return Match("media", {"command": "previous"})

    @rule(r"^stop (?:the )?(?:music|song|video|playback)$")
    def _(m, t):
        return Match("media", {"command": "play_pause"})

    @rule(r"^(?:what's playing|what is playing|what song is this|what's this song|who sings this|"
          r"what's the song|current song)$")
    def _(m, t):
        return Match("now_playing")

    @rule(r"^(?:play|put on|watch)\s+(.+?)\s+on\s+(?:youtube|yt)$|^(?:youtube|search youtube for)\s+(.+)$")
    def _(m, t):
        return Match("youtube", {"query": m.group(1) or m.group(2)})

    @rule(r"^play\s+(.+?)\s+on spotify$")
    def _(m, t):
        return Match("spotify_search", {"query": m.group(1)})

    @rule(r"^(?:play|put on)\s+(.+)$")
    def _(m, t):
        return Match("youtube", {"query": m.group(1)})

    # Screens and windows
    @rule(r"^(?:take a |grab a |take an? )?(?:screenshot|screen shot|screen capture|capture (?:my |the )?screen|"
          r"print screen)(?: of)?(?: (?:this|the|my))?( window)?$")
    def _(m, t):
        return Match("screenshot", {"region": "window" if m.group(1) else "screen"})

    @rule(r"^(?:snip|snipping tool|screenshot (?:an area|part of the screen)|clip (?:part of )?(?:my |the )?screen)$")
    def _(m, t):
        return Match("screenshot", {"region": "snip"})

    @rule(r"^(?:show (?:the |my )?desktop|minimi[sz]e (?:everything|all(?: windows)?)|hide (?:all )?(?:the )?windows)$")
    def _(m, t):
        return Match("window", {"command": "show_desktop"})

    @rule(r"^(minimi[sz]e|maximi[sz]e)(?: (?:this|it|the window|this window|window))?$")
    def _(m, t):
        return Match("window", {"command": "minimize" if "min" in m.group(1) else "maximize"})

    @rule(r"^(?:snap|move|put) (?:this |it |the window |this window )?(?:to the )?(left|right)$")
    def _(m, t):
        return Match("window", {"command": "snap_" + m.group(1)})

    @rule(r"^(?:task view|show (?:me )?all (?:my )?windows)$")
    def _(m, t):
        return Match("window", {"command": "task_view"})

    @rule(r"^(?:lock|lock (?:my |the )?(?:pc|computer|screen|laptop|windows|it))$", safe=False)
    def _(m, t):
        return Match("power", {"command": "lock"}, False)

    @rule(r"^(?:put (?:my |the )?(?:pc|computer|laptop) to sleep|sleep (?:the )?(?:pc|computer|laptop))$", safe=False)
    def _(m, t):
        return Match("power", {"command": "sleep"}, False)

    @rule(r"^(?:restart|reboot) (?:my |the )?(?:pc|computer|laptop|windows)$", safe=False)
    def _(m, t):
        return Match("power", {"command": "restart"}, False)

    @rule(r"^(?:sign out|log out|log off)$", safe=False)
    def _(m, t):
        return Match("power", {"command": "sign_out"}, False)

    @rule(r"^(?:cancel|abort|stop) (?:the )?(?:shutdown|restart)$", safe=False)
    def _(m, t):
        return Match("power", {"command": "cancel_shutdown"}, False)

    @rule(r"^(?:close|quit|exit|kill|shut down|shutdown|terminate|end)\s+(.+)$", safe=False)
    def _(m, t):
        target = re.sub(r"^(?:the|my)\s+", "", m.group(1))
        if target in ("this", "this window", "window", "it", "that", "current window", "that window", "the window"):
            return Match("close_window", {}, False)
        if target in ("pc", "computer", "laptop", "windows") and "shut" in t:
            return Match("power", {"command": "shutdown"}, False)
        if target in ("gem", "jem", "yourself"):
            return Match("quit_gem", {}, False)
        if re.match(r"^(?:gaming|game) mode$", target):
            return Match("gaming_mode", {"on": False})
        return Match("close_app", {"name": target}, False) if _known_app(target) else None

    @rule(r"^(?:switch to|go to|bring up|focus on|show me)\s+(.+)$")
    def _(m, t):
        target = re.sub(r"^(?:the|my)\s+", "", m.group(1))
        if apps.running(target):
            return Match("switch_to", {"name": target})
        if _openable(target):
            return Match("open_app", {"name": target})
        return None

    @rule(r"^(?:open|launch|start|run|fire up|boot up|load|pull up|bring up)\s+(?:up\s+)?(.+)$")
    def _(m, t):
        target = m.group(1)
        if re.match(r"^(?:a |the )?(?:dictation|focus|timer|pomodoro)", target):
            return None
        return Match("open_app", {"name": target}) if _openable(target) else None

    @rule(r"^(?:what(?:'s| is) (?:this|this window|in front|open)|which (?:app|window) is this)$")
    def _(m, t):
        return Match("what_window")

    @rule(r"^(?:open|show) (?:my |the )?(?:latest|last|newest|most recent) download$")
    def _(m, t):
        return Match("open_latest_download")

    @rule(r"^(?:find|open|search for) (?:my |the )?file (?:called |named )?(.+)$", safe=False)
    def _(m, t):
        return Match("find_file", {"name": m.group(1)}, False)

    # System info
    @rule(r"^(?:cpu(?: usage)?|how's my cpu|what's my cpu(?: usage| at)?|processor usage)$")
    def _(m, t):
        return Match("system_info", {"what": "cpu"})

    @rule(r"^(?:ram(?: usage)?|memory usage|how much (?:ram|memory)(?: am i using| is used)?)$")
    def _(m, t):
        return Match("system_info", {"what": "ram"})

    @rule(r"^(?:disk space|storage|how much (?:disk )?space(?: do i have)?(?: left)?|free space|"
          r"how much storage(?: do i have)?(?: left)?)$")
    def _(m, t):
        return Match("system_info", {"what": "disk"})

    @rule(r"^(?:battery(?: level| status)?|how much battery(?: do i have)?(?: left)?|what's my battery(?: at)?)$")
    def _(m, t):
        return Match("system_info", {"what": "battery"})

    @rule(r"^(?:uptime|pc uptime|how long has (?:my |the )?(?:pc|computer|laptop) been (?:on|running))$")
    def _(m, t):
        return Match("system_info", {"what": "uptime"})

    @rule(r"^what's (?:using|eating) (?:my |all my )?(?:memory|ram|cpu)$|^what's slowing (?:down )?my (?:pc|computer)$")
    def _(m, t):
        return Match("system_info", {"what": "top_processes"})

    @rule(r"^what's my (?:ip|ip address)$|^what is my ip(?: address)?$")
    def _(m, t):
        return Match("system_info", {"what": "ip"})

    @rule(r"^(?:system stats|pc stats|system status|system info|how's my pc(?: doing)?|computer stats)$")
    def _(m, t):
        return Match("system_info", {"what": "overview"})

    @rule(r"^(?:ping|test (?:my )?internet|is (?:my )?internet working|"
          r"check (?:my )?(?:internet|connection|wifi))$")
    def _(m, t):
        return Match("ping")

    @rule(r"^(?:turn on |enable |switch to )?dark mode(?: on)?$")
    def _(m, t):
        return Match("dark_mode", {"on": True})

    @rule(r"^(?:turn on |enable |switch to )?light mode(?: on)?$|^(?:turn off|disable) dark mode$|^dark mode off$")
    def _(m, t):
        return Match("dark_mode", {"on": False})

    @rule(r"^(?:set )?(?:the )?brightness (?:to |at )?(.+)$")
    def _(m, t):
        pct = parse_percent(m.group(1))
        return Match("brightness", {"level": pct}) if pct is not None else None

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

    # Small stuff
    @rule(r"^(?:flip a coin|coin flip|heads or tails|toss a coin|flip coin)$")
    def _(m, t):
        return Match("coin_flip")

    @rule(r"^roll (?:a |the |(\d+) )?(?:dice|die|d(\d+))(?: with (\d+) sides)?$")
    def _(m, t):
        return Match("roll_dice", {"count": int(m.group(1) or 1), "sides": int(m.group(2) or m.group(3) or 6)})

    @rule(r"^pick a (?:random )?number (?:between|from) (\d+) (?:and|to) (\d+)$")
    def _(m, t):
        return Match("random_number", {"low": m.group(1), "high": m.group(2)})

    @rule(r"^(?:tell me a joke|joke|tell me another joke|make me laugh|say something funny)$")
    def _(m, t):
        return Match("joke")

    @rule(r"^(?:what can you do|help|help me|what are your commands|how do i use you|how do you work|"
          r"list commands|commands)$")
    def _(m, t):
        return Match("help")

    @rule(r"^(?:repeat(?: that)?|say (?:that|it) again|what did you say|pardon|come again)$")
    def _(m, t):
        return Match("repeat")

    @rule(r"^(?:what did you hear|what did i say|what did you hear me say)$")
    def _(m, t):
        return Match("what_did_you_hear")

    @rule(r"^(?:clear (?:the |our )?(?:conversation|chat|context|history)|start over|new conversation|"
          r"reset (?:the )?conversation)$")
    def _(m, t):
        return Match("clear_conversation")

    @rule(r"^(?:open )?(?:your|gem's|gem) settings$|^open your settings$", safe=False)
    def _(m, t):
        return Match("open_gem_settings", {}, False)

    @rule(r"^(?:open|show)(?: me)?(?: the| my| your)? (dashboard|gem|window|history|conversation history|routines)$",
          safe=False)
    def _(m, t):
        page = "history" if "history" in m.group(1) else "routines" if "routines" in m.group(1) else "home"
        return Match("open_dashboard", {"page": page}, False)

    @rule(r"^(?:what routines do i have|list (?:my )?routines|my routines)$")
    def _(m, t):
        return Match("routine_list")

    # Habits
    @rule(r"^(?:i (?:just )?(?:drank|had|finished) (?:a |another |one |(\d+) )?(?:glass(?:es)?|cups?|bottles?) of water|"
          r"i (?:just )?drank (?:some )?water|log (?:a |(\d+) )?(?:glass(?:es)? of )?water|"
          r"(?:add|plus) (?:a |one )?(?:glass of )?water)$")
    def _(m, t):
        n = next((g for g in m.groups() if g), 1)
        return Match("habit_log", {"habit": "water", "amount": int(n)})

    @rule(r"^i (?:just )?(?:had|drank) (?:a |another |one |(\d+) )?(coffees?|teas?|cups? of coffee|cups? of tea)$")
    def _(m, t):
        return Match("habit_log", {"habit": m.group(2), "amount": int(m.group(1) or 1)})

    @rule(r"^(?:log|add|i did|i just did|i've done|record) (\d+) ([a-z][a-z -]*?)$")
    def _(m, t):
        key = habits.habit_key(m.group(2))
        if key in ("minutes", "seconds", "hours", "percent"):
            return None
        return Match("habit_log", {"habit": m.group(2), "amount": int(m.group(1))})

    @rule(r"^how (?:much|many) ([a-z][a-z -]*?)(?: (?:have i|did i) (?:had|have|done|do|drunk|drink|drank|logged|log))?"
          r"(?: today| this week| so far)?$")
    def _(m, t):
        key = habits.habit_key(m.group(1))
        known = key in habits.UNITS or key in (habits.store.data.get("log") or {})
        return Match("habit_stats", {"habit": key}) if known else None

    # Web
    @rule(r"^(?:search wikipedia for|wikipedia)\s+(.+)$")
    def _(m, t):
        return Match("wikipedia", {"topic": m.group(1)})

    @rule(r"^(?:google|search google for|open results for|show me results for)\s+(?:for\s+)?(.+)$", safe=False)
    def _(m, t):
        return Match("web_search", {"query": m.group(1)}, False)

    @rule(r"^(?:search|look up|search for|search the web for|look up online|find out|check online)\s+"
          r"(?:for\s+)?(.+)$", safe=False)
    def _(m, t):
        return Match("web_answer", {"query": m.group(1)}, False)

    return R


_RULES = None
_raw = ""


def _routine(text):
    from .skills import routines
    return routines.find(text)


def match(text, raw=""):
    """Return a Match for normalized text (raw is the original, for punctuation), or None."""
    global _RULES, _raw
    if _RULES is None:
        _RULES = _rules()
    _raw = raw or text
    for rx, fn, safe in _RULES:
        m = rx.search(text)
        if not m:
            continue
        result = fn(m, text)
        if result is not None:
            if not safe:
                result.safe = False
            return result
    return None
