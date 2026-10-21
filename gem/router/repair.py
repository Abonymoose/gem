"""Second chance for misheard commands, used only when you were clearly talking to Gem and nothing matched.

Speech recognition sometimes gets a word slightly wrong ("spotlite"), splits one ("auto fill"), or mishears
Gem's name at the start ("Jim, pause", "I will highlight ..."). Each repair is only kept if the repaired
sentence then matches a real command, so a repair can never invent something you didn't ask for.
"""
import difflib
import logging
import re

from . import core

log = logging.getLogger("gem.router")

# Filler said before a command, and ways Gem's name gets misheard at the start.
LEADING = (r"^(?:(?:hey|hi|ok|okay|yo|so|um|uh|er|and|like|well|alright)\s+)*"
           r"(?:(?:jim|gym|jen|jam|germ|gemma|gen|jimmy|i will|i'll|i'd|i)\b,?\s+)?")
# Contractions that come through without their apostrophe.
CONTRACTIONS = {"whats": "what's", "wheres": "where's", "hows": "how's", "whos": "who's", "thats": "that's",
                "dont": "don't", "cant": "can't", "im": "i'm", "ive": "i've", "youre": "you're", "isnt": "isn't",
                "wont": "won't", "lets": "let's", "whens": "when's", "theres": "there's", "didnt": "didn't"}
_vocab = None


def _vocabulary():
    """Command words Gem knows: the words written into its rules, plus app names."""
    global _vocab
    if _vocab is None:
        words = set()
        for rx, _, _ in core._rules_list():
            words.update(w for w in re.findall(r"[a-z]{4,}", rx.pattern.lower()))
        try:
            from ..skills.apps import index
            for name in index.entries:
                words.update(w for w in re.findall(r"[a-z]{4,}", name))
        except Exception:
            pass
        _vocab = words
    return _vocab


def _join_pairs(words, vocab):
    """'auto fill' -> 'autofill', 'spot light' -> 'spotlight' when the joined word is a command word."""
    out, i = [], 0
    while i < len(words):
        if i + 1 < len(words) and len(words[i] + words[i + 1]) >= 6 and (words[i] + words[i + 1]) in vocab:
            out.append(words[i] + words[i + 1])
            i += 2
        else:
            out.append(words[i])
            i += 1
    return out


def _fix_words(words, vocab):
    """Swap words that aren't command words for a very close command word ('spotlite' -> 'spotlight')."""
    fixed = []
    for w in words:
        if len(w) >= 5 and w not in vocab and w.isalpha():
            close = difflib.get_close_matches(w, vocab, n=4, cutoff=0.8)
            same_start = [c for c in close if c[0] == w[0]]     # a misheard word nearly always keeps its first sound
            fixed.append((same_start or close or [w])[0])
        else:
            fixed.append(w)
    return fixed


def repair(norm, raw=""):
    """(Match, repaired text) for a sentence that didn't match as heard, or (None, None)."""
    vocab = _vocabulary()
    tries = []
    apostrophes = " ".join(CONTRACTIONS.get(w, w) for w in norm.split())
    if apostrophes != norm:
        tries.append(apostrophes)
        norm = apostrophes
    stripped = re.sub(LEADING, "", norm).strip()
    if stripped and stripped != norm:
        tries.append(stripped)
    for base in [norm] + ([stripped] if stripped and stripped != norm else []):
        words = base.split()
        joined = _join_pairs(words, vocab)
        if joined != words:
            tries.append(" ".join(joined))
        fixed = _fix_words(joined, vocab)
        if fixed != joined:
            tries.append(" ".join(fixed))
    seen = set()
    for t in tries:
        if t in seen or not t:
            continue
        seen.add(t)
        m = core.match(t, raw)
        if m:
            log.info("Heard %r, understood %r", norm, t)
            return m, t
    return None, None
