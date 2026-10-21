"""Normalising speech, shared helpers and matching against the rules in rules/."""
import re
from dataclasses import dataclass, field

from ..skills import apps


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
    t = re.sub(r"^(?:(?:hey|hi|ok|okay|yo|oi)\s+)?%s\b(?!'s|s\b)\s*" % _NAME, "", t.strip())   # keep "gem's ..."
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


def _power_word(words):
    w = (words or "").lower()
    return "sleep" if "sleep" in w else "hibernate" if "hibernate" in w else "restart" if "restart" in w else "shutdown"


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

_RELATIONS = ["sister", "brother", "mom", "mum", "mother", "dad", "father", "friend", "cousin", "grandma", "grandpa",
              "aunt", "uncle", "roommate"]
# Words that can follow "that was" / "block" without being someone's name.
_NOT_NAMES = {"it", "me", "him", "her", "them", "us", "you", "gem", "fun", "close", "easy", "good", "great", "nice",
              "cool", "weird", "wild", "amazing", "sick", "crazy", "insane", "awesome", "funny", "bad", "hard", "fast",
              "quick", "loud", "rude", "random", "everyone", "everybody", "anyone", "nothing", "all", "that", "this",
              "fine", "right", "wrong", "true", "false", "lit", "fire", "clean", "smooth", "lucky", "unlucky", "op",
              "broken", "scary", "sad", "annoying", "perfect", "beautiful", "epic", "brutal", "rough", "ok", "okay"}


# ── Matching ─────────────────────────────────────────────────────────────────

_RULES = None
_raw = ""


def said():
    """What the user actually said (capitals and punctuation intact), for the command being matched."""
    return _raw


def _routine(text):
    from ..skills import routines
    return routines.find(text)


def _rules():
    from .rules import register_all
    R = []

    def rule(pattern, safe=True):
        rx = re.compile(pattern)

        def deco(fn):
            R.append((rx, fn, safe))
            return fn
        return deco

    register_all(rule)
    return R


def _rules_list():
    global _RULES
    if _RULES is None:
        _RULES = _rules()
    return _RULES


def match(text, original=""):
    """Return a Match for normalized text (original is what was said, for punctuation), or None."""
    global _raw
    rules = _rules_list()
    _raw = original or text
    for rx, fn, safe in rules:
        m = rx.search(text)
        if not m:
            continue
        result = fn(m, text)
        if result is not None:
            if not safe:
                result.safe = False
            return result
    return None
