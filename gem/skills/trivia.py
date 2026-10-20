"""Voice trivia: five multiple-choice questions, answer out loud ("B", "the second one", or the answer itself)."""
import logging
import random
import re
import time

from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..cards import card
from ..config import runtime
from ..runtime import svc

log = logging.getLogger("gem.trivia")

TOPICS = ["video games", "movies and TV", "sports and cricket", "music", "science and space", "food and world travel",
          "internet culture and tech", "geography", "animals and nature", "history"]
GEN = """Write {n} fun multiple-choice trivia questions about {topic} for a teenager. Medium difficulty, clearly
correct answers, short questions (under 20 words), 4 short options each, no trick questions, varied answer
positions. Avoid these recent questions: {avoid}
Reply JSON only: {{"questions": [{{"q": "...", "options": ["...", "...", "...", "..."], "answer": 0,
"fact": "one short fun fact about the answer"}}]}}"""
LETTERS = "abcd"
ORDINALS = {"first": 0, "1st": 0, "one": 0, "second": 1, "2nd": 1, "two": 1, "third": 2, "3rd": 2, "three": 2,
            "fourth": 3, "4th": 3, "four": 3, "last": 3}
QUIT = {"stop", "quit", "end", "stop trivia", "end trivia", "quit trivia", "i'm done", "im done", "enough",
        "stop the game", "end the game", "exit"}
SKIP = {"skip", "pass", "next", "i don't know", "i dont know", "no idea", "idk", "dunno", "no clue", "skip it"}

game = {"qs": [], "i": 0, "score": 0, "topic": "", "until": 0.0}
_recent = []


def active():
    if game["qs"] and time.time() > game["until"]:
        game["qs"] = []
    return bool(game["qs"])


def _ask_text(q, n):
    opts = q["options"]
    return "Question %d. %s Is it A, %s; B, %s; C, %s; or D, %s?" % (n, q["q"], opts[0], opts[1], opts[2], opts[3])


def _card(text, reveal=None, last_ok=None):
    q = game["qs"][game["i"]] if game["i"] < len(game["qs"]) else None
    return card("trivia", text, question=q["q"] if q else "", options=q["options"] if q else [],
                number=game["i"] + 1, total=len(game["qs"]), score=game["score"], topic=game["topic"],
                reveal=reveal, last_ok=last_ok)


@action("trivia_start", "Start a voice trivia game: five multiple-choice questions, optionally on a topic.",
        "topic?: str")
def trivia_start(topic=""):
    topic = (topic or "").strip() or random.choice(TOPICS)
    svc.state.update(thinking=True)
    try:
        out = svc.brain.complete(GEN.format(n=5, topic=topic, avoid="; ".join(_recent[-15:]) or "none"),
                                 max_tokens=1400, json_mode=True, temperature=0.9)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    qs = [q for q in (out or {}).get("questions") or []
          if isinstance(q, dict) and q.get("q") and len(q.get("options") or []) == 4
          and isinstance(q.get("answer"), int) and 0 <= q["answer"] < 4][:5]
    if len(qs) < 3:
        raise ActionError("I couldn't come up with good questions just now. Try again?")
    _recent.extend(q["q"] for q in qs)
    game.update(qs=qs, i=0, score=0, topic=topic, until=time.time() + 300)
    return _card("Trivia time: %s, %d questions. %s" % (topic, len(qs), _ask_text(qs[0], 1)))


def _choice(plain, options):
    """Which option (0-3) the user picked, or None."""
    m = re.match(r"^(?:it's |its |it is |i think |i'll go with |ill go with |go with |answer |option |letter |"
                 r"the answer is |my answer is )*(?:option )?([abcd])\b", plain)
    if m:
        return LETTERS.index(m.group(1))
    for word, i in ORDINALS.items():
        if re.search(r"\b(?:the )?%s(?: one| option)?\b" % word, plain) and len(plain.split()) <= 5:
            return i
    words = set(re.findall(r"[a-z0-9]+", plain))
    best, best_hits = None, 0
    for i, opt in enumerate(options):
        ow = set(re.findall(r"[a-z0-9]+", opt.lower())) - {"the", "a", "an", "of"}
        hits = len(ow & words)
        if ow and hits / len(ow) >= 0.5 and hits > best_hits:
            best, best_hits = i, hits
    return best


def answer(text, plain):
    """Handle a reply during the game. Returns what to say, or None if it isn't an answer."""
    if plain in QUIT:
        n, s = len(game["qs"]), game["score"]
        game["qs"] = []
        return "Game over. You got %d out of %d." % (s, n)
    q = game["qs"][game["i"]]
    if plain in SKIP:
        pick = -1
    else:
        pick = _choice(plain, q["options"])
        if pick is None:
            return None
    right = q["answer"]
    ok = pick == right
    game["score"] += 1 if ok else 0
    lead = "Correct! " if ok else ("Skipped. " if pick == -1 else "Not quite. ")
    said = lead + ("" if ok else "It was %s, %s. " % (LETTERS[right].upper(), q["options"][right])) + \
        (q.get("fact", "").strip() + " " if q.get("fact") else "")
    reveal = {"right": right, "picked": pick}
    game["i"] += 1
    game["until"] = time.time() + 300
    if game["i"] >= len(game["qs"]):
        n, s = len(game["qs"]), game["score"]
        best = runtime.data.get("trivia_best", 0)
        if s > best:
            with runtime as d:
                d["trivia_best"] = s
        verdict = ("Perfect score!" if s == n else "Nice one." if s >= n * 0.6 else "Better luck next round.")
        game["qs"] = []
        return card("trivia", "%sThat's the game: %d out of %d. %s%s" % (
            said, s, n, verdict, " New personal best!" if s > best and best else ""),
            done=True, score=s, total=n, topic=game["topic"], question="", options=[])
    return _card(said + "Next. " + _ask_text(game["qs"][game["i"]], game["i"] + 1), reveal=reveal,
                 last_ok=None if pick == -1 else ok)
