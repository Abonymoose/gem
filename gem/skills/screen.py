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


def grab():
    """(PIL image of the monitor you're on, active window title), with the island hidden."""
    from PIL import ImageGrab
    if svc.overlay:
        svc.overlay.suppress(1.2)            # keep the island out of the picture
        time.sleep(0.35)
    hwnd = foreground_window()
    box = monitor_rect_physical(hwnd) if hwnd else None
    img = ImageGrab.grab(bbox=box, all_screens=True) if box else ImageGrab.grab()
    img = img.convert("RGB")
    img.thumbnail((1600, 1600))
    return img, window_title(hwnd) if hwnd else ""


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
    question = (question or "").strip() or "What's on my screen? Explain the important part."
    svc.state.update(thinking=True)
    url, title = _capture()
    try:
        answer = svc.brain.see(INSTRUCTION.format(title=title or "unknown"), question, url)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    if not answer:
        raise ActionError("I couldn't read the screen just now.")
    log.info("Screen question %r -> %d chars", question, len(answer))
    return card("screen", answer)
