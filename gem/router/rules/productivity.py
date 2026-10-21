"""Commands: To-dos, notes, screen memory, memory, focus, briefing and weather."""
import re

from ...parse import parse_duration
from ..core import Match, said


def register(rule):
    # To-do and notes
    @rule(r"^(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my |the )?(?:to ?do|to-do|todo|task|tasks|shopping)?\s*list$",
          safe=False)
    def _(m, t):
        # Commas are gone from the normalized text, so split on the raw words.
        raw = re.search(r"(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my |the )?[\w -]*list", said().lower())
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

    # Screen memory
    @rule(r"^(?:remember|save|keep|bookmark) (?:this|that|this page|this screen|what's on (?:my|the) screen|"
          r"my screen|the screen|this one|that one)(?: for later)?(?: (?:as|called|under) (.+))?$")
    def _(m, t):
        return Match("screen_save", {"note": m.group(1) or ""})

    @rule(r"^(?:what was|show me|find|pull up|bring up|where's|where is|open) (?:that|the) (.+?) (?:i |that i )"
          r"(?:saved|remembered|screenshotted|bookmarked)(?: earlier| yesterday| today| last week| before)?$|"
          r"^what did i save about (.+)$|^(?:find|show me|pull up) (?:my |the )?saved screens? (?:about|of|with) (.+)$")
    def _(m, t):
        return Match("screen_find", {"query": next(g for g in m.groups() if g)})

    @rule(r"^(?:what (?:screens )?(?:did|have) i saved?(?: today| recently| this week)?|(?:show|list)(?: me)? (?:my |the )?"
          r"saved screens|my saved screens)$")
    def _(m, t):
        return Match("screen_list")

    @rule(r"^(?:open|show) (?:it|that|the screenshot) (?:full ?screen|full ?size|bigger)$")
    def _(m, t):
        return Match("screen_open")

    # Memory
    @rule(r"^what do you (?:remember|know) about me$|^what have i told you to remember$|"
          r"^what do you know$|^tell me what you know about me$")
    def _(m, t):
        return Match("memories")

    @rule(r"^remember (?:that )?(.+)$", safe=False)
    def _(m, t):
        if m.group(1).startswith("to ") or m.group(1) in ("this", "that", "it"):
            return None                         # "remember to call mom" is a task; let the AI decide
        return Match("remember", {"fact": m.group(1)}, False)

    @rule(r"^forget (?:that |about )?(.+)$", safe=False)
    def _(m, t):
        if re.match(r"^my voice(?:print| profile)?$", m.group(1)):
            return Match("voice_forget", {}, False)
        voice = re.match(r"^(.+?)(?:'s| s) voice$", m.group(1))
        if voice:
            return Match("voice_forget", {"person": voice.group(1)}, False)
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
