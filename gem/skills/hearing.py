"""Teaching Gem words it keeps mishearing, and correcting the last thing it heard.

"When I say free ya I mean Freya" saves a fix that's applied to everything Gem hears from then on.
"No, I said Spotify" runs that instead of what Gem heard; "I said Spotify, not spot if I" also learns the fix
and re-runs your last request with it corrected.
"""
import difflib
import logging
import re
import time

from ..actions import action
from ..config import JsonStore
from ..runtime import svc

log = logging.getLogger("gem.hearing")

store = JsonStore("hearing.json", {"fixes": {}})
RECENT = 90             # seconds a "no, I said ..." can still refer back to


def _pattern(heard):
    return re.compile(r"(?<![\w'])%s(?![\w'])" % r"\s+".join(map(re.escape, heard.split())), re.I)


def apply(text):
    """Everything Gem hears, with your taught fixes swapped in."""
    fixes = store.data.get("fixes") or {}
    if not text or not fixes:
        return text
    out = text
    for heard in sorted(fixes, key=len, reverse=True):
        out = _pattern(heard).sub(fixes[heard], out)
    if out != text:
        log.info("Hearing fix: %r -> %r", text, out)
    return out


def _clean(words):
    return re.sub(r"\s+", " ", re.sub(r"[^\w' -]", " ", words or "")).strip().strip("'")


def _previous():
    """The request before the correction, if it was recent."""
    a = svc.assistant
    if not a or len(a.last_heard) < 2 or time.time() - getattr(a, "last_heard_at", 0) > RECENT:
        return None
    return a.last_heard[-2]


@action("hearing_teach", "Remember that a word or phrase Gem keeps mishearing means something else.",
        "heard: str, meant: str")
def hearing_teach(heard, meant):
    heard, meant = _clean(heard).lower(), _clean(meant)
    if not heard or not meant or heard == meant.lower():
        return "Tell me what I hear and what you mean, like: when I say free ya, I mean Freya."
    if heard in ("gem", "jem") or len(heard) < 2:
        return "I'd rather not change how I hear my own name."
    with store as data:
        data.setdefault("fixes", {})[heard] = meant
    return "Got it. When I hear %s, I'll take it as %s." % (heard, meant)


# Too common to learn a fix for from one edited word.
_COMMON = {"the", "a", "an", "to", "and", "or", "of", "in", "on", "at", "for", "it", "is", "my", "me", "you", "your",
           "this", "that", "i", "we", "be", "do", "go", "up", "off", "can", "please", "what", "how"}


def learn_from_edit(heard, fixed):
    """You fixed what Gem heard in the typing bar. One word or short phrase swapped the same way twice is learned
    (once could be a change of mind). Returns what to tell you, or None."""
    a = _clean(heard).lower().split()
    b = _clean(fixed).split()
    ops = [o for o in difflib.SequenceMatcher(None, a, [w.lower() for w in b]).get_opcodes() if o[0] != "equal"]
    if len(ops) != 1 or ops[0][0] != "replace":
        return None
    _, i1, i2, j1, j2 = ops[0]
    old, new = " ".join(a[i1:i2]), " ".join(b[j1:j2])
    if i2 - i1 > 3 or j2 - j1 > 3 or old in ("gem", "jem") or (i2 - i1 == 1 and (len(old) < 3 or old in _COMMON)):
        return None
    key = "%s -> %s" % (old, new.lower())
    with store as data:
        seen = data.setdefault("edits", {})
        seen[key] = seen.get(key, 0) + 1
        if seen[key] < 2:
            return None
        seen.pop(key)
    hearing_teach(old, new)
    return "I'll hear %s as %s from now on." % (old, new)


@action("hearing_forget", "Stop applying a taught hearing fix, or all of them.", "heard?: str")
def hearing_forget(heard=""):
    heard = _clean(heard).lower()
    with store as data:
        fixes = data.setdefault("fixes", {})
        if not heard or heard in ("all", "everything", "all of them", "them all"):
            n = len(fixes)
            fixes.clear()
            return "Cleared %d word fix%s." % (n, "" if n == 1 else "es") if n else "There weren't any word fixes."
        key = heard if heard in fixes else next((k for k, v in fixes.items() if v.lower() == heard), None)
        if not key:
            return "I don't have a fix for %s." % heard
        fixes.pop(key)
    return "Okay, I'll hear %s as it sounds again." % key


@action("hearing_list", "List the words Gem was taught to hear differently.")
def hearing_list():
    fixes = store.data.get("fixes") or {}
    if not fixes:
        return "You haven't taught me any words yet. Say: when I say this, I mean that."
    pairs = ["%s means %s" % (k, v) for k, v in list(fixes.items())[:8]]
    return "I've learned %d: %s." % (len(fixes), "; ".join(pairs))


@action("said_instead", "The user corrects what Gem heard: run what they actually said (optionally learning the fix).",
        "said: str, not_this?: str")
def said_instead(said, not_this=""):
    said, wrong = _clean(said), _clean(not_this)
    if not said:
        return "What did you say?"
    command = said
    if wrong:
        learned = len(wrong.split()) <= 4 and wrong.lower() not in ("that", "this", "it")
        if learned:
            hearing_teach(wrong, said)
        before = _previous()
        if not (before and _pattern(wrong).search(before)):
            # Nothing recent to redo; the fix still applies from now on.
            return ("Got it, I'll hear %s as %s from now on." % (wrong.lower(), said)) if learned else \
                "Okay. Say the whole thing again and I'll get it this time."
        command = _pattern(wrong).sub(said, before)
    log.info("Correction: running %r", command)
    svc.assistant.submit_text(command)
    return None
