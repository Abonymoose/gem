"""Commands: Small stuff and habits."""
from ...skills import habits
from ..core import Match


def register(rule):
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

    # Unsafe: said to someone else in the room, these would make Gem talk over the conversation.
    @rule(r"^(?:what can you do|help|help me|what are your commands|how do i use you|how do you work|"
          r"list commands|commands)$", safe=False)
    def _(m, t):
        return Match("help")

    @rule(r"^(?:repeat(?: that)?|say (?:that|it) again|what did you say|pardon|come again)$", safe=False)
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
