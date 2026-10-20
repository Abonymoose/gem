"""Screen memory: "remember this" saves what's on screen with a short AI description, so you can find it later.

Only when you ask; nothing is captured in the background. Saved in the data folder (screens/).
"""
import datetime
import logging
import os
import re
import time
import uuid

from ..actions import ActionError, action
from ..brain import BrainUnavailable, _parse_json
from ..cards import card
from ..config import DATA_DIR, JsonStore
from ..runtime import svc
from .screen import data_url, grab

log = logging.getLogger("gem.screen_memory")

SCREENS_DIR = os.path.join(DATA_DIR, "screens")
index = JsonStore("screens.json", {"items": []})
_last_shown = None

DESCRIBE = (
    "You're saving a screenshot so the user can find it later by asking for it in their own words. The active "
    "window is titled: {title}. Reply with JSON only: {{\"title\": \"what it is, under 8 words\", \"summary\": "
    "\"one or two plain sentences on what's shown and why it might matter\", \"keywords\": [\"10 to 15 words or "
    "names someone might use to ask for it later\"], \"details\": \"specific names, prices, numbers, dates, links "
    "or codes visible, or empty\"}}")
STOP = {"the", "a", "an", "that", "this", "what", "was", "i", "my", "me", "about", "saved", "save", "screen",
        "screenshot", "thing", "one", "show", "find", "remember", "remembered", "from", "with", "for", "of", "on",
        "it", "to", "is", "did", "do", "you", "page", "earlier", "yesterday", "today", "last", "week"}


def _when(t):
    dt = datetime.datetime.fromtimestamp(t)
    today = datetime.date.today()
    day = "today" if dt.date() == today else "yesterday" if (today - dt.date()).days == 1 else dt.strftime("%A %b %d")
    return "%s at %s" % (day, dt.strftime("%I:%M %p").lstrip("0"))


def _card(item, text):
    return card("image", text, path=item["path"], header="Saved screen", note="%s · %s" % (item["title"], _when(item["t"])))


@action("screen_save", "Save what's on screen for later (screen memory), optionally with a note.", "note?: str")
def screen_save(note=""):
    svc.state.update(thinking=True)
    img, title = grab()
    os.makedirs(SCREENS_DIR, exist_ok=True)
    sid = uuid.uuid4().hex[:10]
    path = os.path.join(SCREENS_DIR, "%s_%s.jpg" % (datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), sid))
    img.save(path, "JPEG", quality=80)
    info = {}
    try:
        info = _parse_json(svc.brain.see(DESCRIBE.format(title=title or "unknown"), "Describe this screen.",
                                         data_url(img), max_tokens=350)) or {}
    except BrainUnavailable as e:
        log.warning("Saved the screen without a description: %s", e)
    item = {"id": sid, "t": time.time(), "path": path, "window": title, "note": (note or "").strip(),
            "title": (info.get("title") or title or "Screen").strip()[:80], "summary": info.get("summary") or "",
            "keywords": [str(k) for k in info.get("keywords") or []][:20], "details": info.get("details") or ""}
    with index as data:
        data["items"].append(item)
        del data["items"][:-500]
    global _last_shown
    _last_shown = path
    return _card(item, "Saved: %s." % item["title"])


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 1}


def _search(query):
    items = index.data.get("items") or []
    q = _words(query)
    scored = []
    for i, it in enumerate(items):
        hay = _words(" ".join([it["title"], it["summary"], " ".join(it["keywords"]), it["details"], it["window"],
                               it.get("note", "")]))
        hits = len(q & hay) + 0.5 * sum(1 for w in q for h in hay if len(w) > 3 and (w in h or h in w) and w != h)
        if hits:
            scored.append((hits + i * 1e-4, it))           # ties go to the newer one
    scored.sort(key=lambda s: -s[0])
    if scored:
        return scored[0][1]
    if not items or not q:
        return None
    # Nothing matched word for word: let the AI pick by meaning.
    listing = "\n".join("%d. %s: %s" % (n, it["title"], it["summary"]) for n, it in enumerate(items[-60:]))
    try:
        out = svc.brain.complete('Pick the saved screen that best matches the request. Reply JSON {"index": n} or '
                                 '{"index": null} if none fits.', "Request: %s\n\n%s" % (query, listing),
                                 max_tokens=60, json_mode=True, temperature=0)
        n = (out or {}).get("index")
        return items[-60:][int(n)] if n is not None else None
    except Exception:
        return None


@action("screen_find", "Find a screen the user saved earlier (screen memory) by what was on it.", "query: str")
def screen_find(query=""):
    if not index.data.get("items"):
        return "You haven't saved any screens yet. Say remember this when something's worth keeping."
    global _last_shown
    item = _search(query or "")
    if not item or not os.path.exists(item["path"]):
        return "I couldn't find a saved screen like that."
    _last_shown = item["path"]
    text = item["summary"] or item["title"]
    if item.get("details"):
        text += " " + item["details"]
    return _card(item, text)


@action("screen_open", "Open the most recently shown or saved screen full size.")
def screen_open():
    items = index.data.get("items") or []
    if not items:
        raise ActionError("There's no saved screen to open.")
    path = _last_shown if _last_shown and os.path.exists(_last_shown) else items[-1]["path"]
    os.startfile(path)
    return None


@action("screen_list", "List the screens the user saved recently.")
def screen_list():
    items = index.data.get("items") or []
    if not items:
        return "You haven't saved any screens yet."
    recent = items[-6:][::-1]
    rows = [{"icon": "dot", "text": "%s · %s" % (it["title"], _when(it["t"]))} for it in recent]
    n = len(items)
    return card("briefing", "You've saved %d screen%s. The latest: %s." % (n, "" if n == 1 else "s", ", ".join(
        it["title"] for it in recent[:3])), greeting="Saved screens", rows=rows)
