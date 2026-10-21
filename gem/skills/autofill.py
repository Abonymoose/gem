"""Autofill suggestions: Gem looks at the screen, finds what needs filling (an empty spreadsheet cell, a maths
question, a blank in a form) and shows what goes there right next to it. The first one is copied, so you
click the spot and paste. Gem never types into your apps itself.
"""
import logging
import re
import time

from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..runtime import svc
from ..winapi import set_clipboard
from .screen import _facts, grab, look

log = logging.getLogger("gem.autofill")

ASK = (
    "You are Gem, helping the user fill something in on their screen. The window is titled: {title}. They asked: "
    "{request}\nFind the spots that need filling, most relevant first (at most 6): an empty spreadsheet cell where a "
    "total, average or other formula belongs, a maths question without an answer, a blank in a form or worksheet. "
    "For each, give exactly what to put there:\n"
    "- spreadsheets: a formula starting with =, using the real column letters and row numbers you can see on screen "
    "(for example =SUM(B2:B10)); prefer simple, standard formulas;\n"
    "- maths: work it out carefully step by step in your head and give only the final answer, with units if any;\n"
    "- anything else: the shortest correct text.\n"
    "For a blank, give only what gets written in the blank itself (for \"x = ____\" just the number, not \"x = 5\").\n"
    "Only use what you can actually read on the screen. Read numbers character by character and never invent data. "
    "If nothing needs filling, say so and return no fills. True facts about this PC, if relevant: {facts}.\n")
BOX_RULE = (
    "\"blank\" is true when there's an empty place on screen where the answer gets written (an empty cell, an "
    "answer line like ____, an empty box or field); then \"box\" is exactly that empty place. Otherwise \"blank\" is "
    "false and \"box\" is the question or item the answer belongs to.")
TILED = ASK + (
    "You get the screen as {{n}} overlapping square pieces from left to right: image 1 is the leftmost part. Reply with "
    "JSON only: {{\"answer\": \"one or two spoken sentences: what you found and the first suggestion\", \"fills\": "
    "[{{\"label\": \"where it goes, a few words (e.g. B11 total)\", \"image\": 1, \"blank\": true, \"box\": [x1, y1, "
    "x2, y2], \"text\": \"what to put there\", \"why\": \"a few words of working\"}}]}}. " + BOX_RULE +
    " Box coordinates are integers 0-1000 across that piece.")
SINGLE = ASK + (
    "The black band at the bottom of the image is padding; ignore it. Reply with JSON only: {{\"answer\": \"one or two "
    "spoken sentences: what you found and the first suggestion\", \"fills\": [{{\"label\": \"where it goes, a few "
    "words\", \"blank\": true, \"box\": [x1, y1, x2, y2], \"text\": \"what to put there\", \"why\": \"a few words of "
    "working\"}}]}}. " + BOX_RULE + " Box coordinates are integers 0-1000 across the whole image.")


def _is_dark(img, box):
    """Is the screen under this box dark? (so the overlay writes in a light colour there)"""
    W, H = img.size
    crop = img.crop((int(box[0] * W), int(box[1] * H), max(int(box[0] * W) + 1, int(box[2] * W)),
                     max(int(box[1] * H) + 1, int(box[3] * H)))).convert("L")
    hist = crop.histogram()
    total = sum(hist) or 1
    return sum(i * n for i, n in enumerate(hist)) / total < 110

last = {"t": 0.0, "fills": []}
ORDINAL = {"first": 1, "1st": 1, "one": 1, "second": 2, "2nd": 2, "two": 2, "third": 3, "3rd": 3, "three": 3,
           "fourth": 4, "4th": 4, "four": 4, "last": -1}


def _spoken(text):
    """Formulas read out more naturally: '=SUM(B2:B10)' -> 'equals SUM of B2 to B10'."""
    t = re.sub(r"^=", "equals ", text)
    t = re.sub(r"([A-Z]+\d+):([A-Z]+\d+)", r"\1 to \2", t)
    return t.replace("(", " of ").replace(")", "")


@action("autofill", "Look at the screen and suggest what to fill in: spreadsheet formulas for empty cells, answers to "
        "maths questions, blanks in forms. Shows each suggestion next to its spot and copies the first one (the user "
        "pastes it). Gem never types into apps.", "request?: str")
def autofill(request=""):
    request = (request or "").strip() or "Fill in what's missing."
    svc.state.update(thinking=True)
    img, title, monitor = grab(with_box=True, full=True)
    facts = _facts()
    try:
        out, raw, to_box, _ = look(img, request, TILED.format(title=title or "unknown", request=request, facts=facts),
                                   SINGLE.format(title=title or "unknown", request=request, facts=facts),
                                   max_tokens=700)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    if not out:
        return raw.strip() or "I couldn't work out what to fill in."
    fills = []
    for f in (out.get("fills") or [])[:6]:
        if not isinstance(f, dict) or not str(f.get("text") or "").strip():
            continue
        box = to_box(f)
        fills.append({"box": box, "label": str(f.get("label") or "")[:30], "text": str(f["text"]).strip()[:120],
                      "why": str(f.get("why") or "").strip()[:80],
                      "blank": bool(f.get("blank")) and box is not None,
                      "dark": _is_dark(img, box) if box else False})
    answer = str(out.get("answer") or "").strip()
    if not fills:
        return answer or "I don't see anything that needs filling in."
    last.update(t=time.time(), fills=fills, copied=1)
    set_clipboard(fills[0]["text"])
    shown = [f for f in fills if f["box"]]
    if shown and svc.overlay and hasattr(svc.overlay, "suggest"):
        svc.overlay.suggest(monitor, [dict(f, n=i) for i, f in enumerate(fills, 1) if f["box"]], seconds=40.0)
    log.info("Autofill: %d suggestion(s), %d placed", len(fills), len(shown))
    tail = " The first one's copied, so click the spot and paste."
    if len(fills) > 1:
        tail += " Say copy the second one for the next."
    return (answer or "Here's what goes there: %s." % _spoken(fills[0]["text"])) + tail


@action("autofill_copy", "Copy one of the autofill suggestions Gem just showed (1 = first).", "number: number")
def autofill_copy(number=1):
    fills = last["fills"] if time.time() - last["t"] < 15 * 60 else []
    if not fills:
        raise ActionError("There's nothing to copy yet. Say autofill first.")
    n = int(number if number is not None else 1)
    n = len(fills) if n == -1 else (last.get("copied", 1) + 1 if n == 0 else n)    # -1 last, 0 next
    if not 1 <= n <= len(fills):
        raise ActionError("There are only %d suggestions." % len(fills))
    set_clipboard(fills[n - 1]["text"])
    last["copied"] = n
    return "Copied %s." % ("number %d" % n if len(fills) > 1 else "it")
