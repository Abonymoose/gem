"""What should I watch / play: three picks that fit your mood and what Gem knows you like."""
import logging
import random

from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..cards import card
from ..config import JsonStore
from ..runtime import svc

log = logging.getLogger("gem.picks")

recent = JsonStore("picks.json", {"recent": []})

INSTRUCTION = """You recommend things for {name} to {verb}. Return JSON only:
{{"picks": [{{"title": "...", "kind": "movie|show|anime|youtube|game", "why": "a short reason, under 8 words"}}]}}
Exactly 3 picks, well known and easy to find. Match the mood if given.
For games, prefer games from their installed apps when they fit, and include at least one they don't have.
Don't repeat anything from "recently suggested". Mix it up; avoid the most obvious answers."""


def _installed(title):
    from .apps import index
    t = title.lower().replace(":", "").strip()
    return any(t == n or (len(t) > 4 and (t in n or n in t)) for n in index.entries)


def _context(kind):
    from .apps import index
    from .insights import _totals
    from .productivity import memory
    lines = []
    facts = (memory.data.get("facts") or [])[-20:]
    if facts:
        lines.append("Things they told Gem: " + "; ".join(facts))
    try:
        top = sorted(_totals(14).items(), key=lambda kv: -kv[1])[:10]
        if top:
            lines.append("Where their screen time goes (2 weeks): " + ", ".join("%s %dh" % (k, v // 3600) for k, v in top))
    except Exception:
        pass
    if kind == "play" and index.entries:
        lines.append("Installed apps (pick out the games): " + ", ".join(sorted(n.title() for n in index.entries)))
    lines.append("Recently suggested: " + (", ".join(recent.data.get("recent", [])[-15:]) or "nothing"))
    return "\n".join(lines)


@action("picks", "Recommend three things to watch or play, fitting the user's mood and tastes.",
        "kind: watch|play, mood?: str")
def picks(kind="watch", mood=""):
    kind = "play" if str(kind).lower().startswith(("play", "game")) else "watch"
    verb = "play (video games)" if kind == "play" else "watch (movies, shows, anime or YouTube)"
    ask = "Mood or request: %s\n\n%s" % (mood or "none given", _context(kind))
    svc.state.update(thinking=True)
    try:
        out = svc.brain.complete(INSTRUCTION.format(name=svc.config.get("user_name") or "the user", verb=verb), ask,
                                 max_tokens=450, json_mode=True, temperature=0.9)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    items = [p for p in (out or {}).get("picks") or [] if isinstance(p, dict) and p.get("title")][:3]
    if not items:
        raise ActionError("I couldn't come up with picks just now.")
    with recent as data:
        data["recent"] = (data.get("recent", []) + [p["title"] for p in items])[-30:]
    names = [p["title"] for p in items]
    say = "How about %s?" % (", ".join(names[:-1]) + " or " + names[-1] if len(names) > 1 else names[0])
    title = random.choice(["Tonight's picks", "Worth a watch", "Try these"]) if kind == "watch" \
        else random.choice(["What to play", "Game picks", "Try these"])
    rows = [{"title": p["title"], "why": p.get("why", ""), "kind": p.get("kind", ""),
             "installed": kind == "play" and _installed(p["title"])} for p in items]
    return card("picks", say, title=title, rows=rows)
