"""Explain my screen: a screenshot of the monitor you're on, answered by a vision model. Read only."""
import base64
import io
import logging
import time

from ..actions import ActionError, action
from ..brain import BrainUnavailable
from ..cards import card
from ..runtime import svc
from ..winapi import foreground_window, monitor_rect_physical, window_title

log = logging.getLogger("gem.screen")

INSTRUCTION = (
    "You are Gem, a voice assistant looking at a screenshot of the user's screen. The window they're using is "
    "titled: {title}. Answer their question about what's on screen for someone listening: two to four short plain "
    "sentences, no markdown, lists or URLs. Be specific about what you can actually see (names, numbers, error "
    "text). If it's an error, say what it means and the most likely fix. If you can't make it out, say so.")
# Same, but also pointing at what the answer is about, so Gem can outline it on screen.
POINT = INSTRUCTION + (
    " The black band at the bottom of the image is padding; ignore it. Reply with JSON only: {{\"answer\": \"...\", "
    "\"highlights\": [{{\"label\": \"two or three words\", \"box\": [x1, y1, x2, y2]}}]}}. Box coordinates are "
    "integers from 0 to 1000 across the whole image (0,0 top left, 1000,1000 bottom right). Highlight the exact "
    "thing the answer is about (the error text, the button, the paragraph), at most 3, tight boxes. Use an empty "
    "list if nothing specific fits.")


def grab(with_box=False):
    """(PIL image of the monitor you're on, active window title[, monitor rect in physical px]), island hidden."""
    from PIL import ImageGrab
    if svc.overlay:
        svc.overlay.suppress(1.2)            # keep the island (and any highlight) out of the picture
        time.sleep(0.35)
    hwnd = foreground_window()
    box = monitor_rect_physical(hwnd) if hwnd else None
    img = ImageGrab.grab(bbox=box, all_screens=True) if box else ImageGrab.grab()
    img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    title = window_title(hwnd) if hwnd else ""
    if with_box:
        return img, title, box or (0, 0, img.width, img.height)
    return img, title


def _squared(img, size=1280):
    """The screenshot on a square canvas: the vision model measures both axes the same way, so its
    0-1000 coordinates map back exactly. Returns (square image, scale x, scale y) to get back to 0..1."""
    from PIL import Image
    small = img.copy()
    small.thumbnail((size, size))
    side = max(small.size)
    square = Image.new("RGB", (side, side), (0, 0, 0))
    square.paste(small, (0, 0))
    return square, side / 1000.0 / small.width, side / 1000.0 / small.height


def _boxes(raw, sx, sy):
    """Model boxes -> [((x1, y1, x2, y2) as 0..1 of the screen, label)], sanity-checked."""
    out = []
    for h in (raw or [])[:3]:
        try:
            x1, y1, x2, y2 = [float(v) for v in h["box"]]
        except (KeyError, TypeError, ValueError):
            continue
        x1, x2 = sorted((x1 * sx, x2 * sx))
        y1, y2 = sorted((y1 * sy, y2 * sy))
        x1, y1, x2, y2 = max(0.0, x1), max(0.0, y1), min(1.0, x2), min(1.0, y2)
        if x2 - x1 < 0.004 or y2 - y1 < 0.004 or (x2 - x1) * (y2 - y1) > 0.85:
            continue                          # too small to be real, or basically the whole screen
        out.append(((x1, y1, x2, y2), str(h.get("label") or "")[:28]))
    return out


def data_url(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _capture():
    img, title = grab()
    return data_url(img), title


@action("explain_screen", "Look at the user's screen and answer a question about it: explain an error, summarize "
        "a page, read something out, say what's going on.", "question?: str")
def explain_screen(question=""):
    from ..brain import _parse_json
    question = (question or "").strip() or "What's on my screen? Explain the important part."
    svc.state.update(thinking=True)
    img, title, monitor = grab(with_box=True)
    square, sx, sy = _squared(img)
    try:
        raw = svc.brain.see(POINT.format(title=title or "unknown"), question, data_url(square), max_tokens=500)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    out = _parse_json(raw)
    if not isinstance(out, dict) or "answer" not in out:
        out = None                            # plain text answer: still fine, just nothing to outline
    answer = (out["answer"] if out else raw).strip()
    if not answer:
        raise ActionError("I couldn't read the screen just now.")
    boxes = _boxes((out or {}).get("highlights"), sx, sy)
    if boxes and svc.overlay and hasattr(svc.overlay, "highlight") and (svc.config.get("appearance") or {}).get(
            "screen_highlights", True):
        svc.overlay.highlight(monitor, boxes, seconds=max(7.0, len(answer) / 13.0))
    log.info("Screen question %r -> %d chars, %d highlight(s)", question, len(answer), len(boxes))
    return card("screen", answer)


@action("spotlight", "Dim everything on screen except the window in front, to help focus (follows the active "
        "window), or turn it off.", "on: bool")
def spotlight(on=True):
    if not svc.overlay or not hasattr(svc.overlay, "spotlight"):
        raise ActionError("The spotlight isn't available right now.")
    svc.overlay.spotlight(bool(on))
    return None if on else "Spotlight off."


@action("clear_highlights", "Remove the outlines Gem drew on screen.")
def clear_highlights():
    if svc.overlay:
        svc.overlay.dismiss()
    return None
