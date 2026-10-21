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


def grab(with_box=False, full=False):
    """(PIL image of the monitor you're on, active window title[, monitor rect in physical px]), island hidden.
    full=True keeps every pixel (for pointing at things); otherwise it's shrunk to 1600 px."""
    from PIL import ImageGrab
    if svc.overlay:
        svc.overlay.suppress(1.2)            # keep the island (and any highlight) out of the picture
        time.sleep(0.35)
    hwnd = foreground_window()
    box = monitor_rect_physical(hwnd) if hwnd else None
    img = ImageGrab.grab(bbox=box, all_screens=True) if box else ImageGrab.grab()
    img = img.convert("RGB")
    if not full:
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


REFINE = ("This is a zoomed-in part of the user's screen (any black band at the bottom or right is padding; ignore "
          "it). The user asked: {question}. Find each of these:\n{targets}\nReply with JSON only: {{\"boxes\": "
          "[[x1, y1, x2, y2], ...]}} in the same order, one per item, using integers from 0 to 1000 across the whole "
          "image (0,0 top left, 1000,1000 bottom right), as tight as possible around each. Use null for an item that "
          "isn't in this picture.")
REFINE_COST = 3500          # what one picture costs against the vision model's per-minute allowance


def _around(boxes, W, H):
    """A crop (0..1) around boxes, with enough room that the real things are inside even if the first look was off."""
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    mx, my = max((x2 - x1) * 0.6, 220.0 / W), max((y2 - y1) * 0.6, 160.0 / H)
    return max(0.0, x1 - mx), max(0.0, y1 - my), min(1.0, x2 + mx), min(1.0, y2 + my)


def refine(img, boxes, question):
    """A second, zoomed-in look at full resolution to tighten rough boxes, in one request.
    boxes: [((x1, y1, x2, y2) 0..1 of img, label)]. Returns the same list, sharpened where it worked."""
    from ..brain import _parse_json
    if not boxes:
        return boxes
    W, H = img.size
    crop_box = _around([b for b, _ in boxes], W, H)
    targets = boxes
    if (crop_box[2] - crop_box[0]) * (crop_box[3] - crop_box[1]) > 0.4:
        # Spread across the screen: zooming out to fit them all wouldn't help, so sharpen the main one.
        targets = boxes[:1]
        crop_box = _around([boxes[0][0]], W, H)
    cx1, cy1, cx2, cy2 = crop_box
    crop = img.crop((int(cx1 * W), int(cy1 * H), int(cx2 * W), int(cy2 * H)))
    square, sx, sy = _squared(crop, size=1024)
    listing = "\n".join("%d) %s" % (i + 1, label or "the thing being pointed at") for i, (_, label) in enumerate(targets))
    try:
        out = _parse_json(svc.brain.see(REFINE.format(question=question, targets=listing), "Where are they?",
                                        data_url(square), max_tokens=200))
    except BrainUnavailable:
        return boxes                                 # out of quota for now: the rough boxes will do
    found = (out or {}).get("boxes") if isinstance(out, dict) else None
    if not isinstance(found, list):
        return boxes
    cw, ch = cx2 - cx1, cy2 - cy1
    sharp = list(boxes)
    for i, b in enumerate(found[:len(targets)]):
        try:
            bx1, by1, bx2, by2 = [float(v) for v in b]
        except (TypeError, ValueError):
            continue
        bx1, bx2 = sorted((max(0.0, bx1 * sx), min(1.0, bx2 * sx)))
        by1, by2 = sorted((max(0.0, by1 * sy), min(1.0, by2 * sy)))
        new = (cx1 + bx1 * cw, cy1 + by1 * ch, cx1 + bx2 * cw, cy1 + by2 * ch)
        if (new[2] - new[0]) * W < 6 or (new[3] - new[1]) * H < 6 or (bx2 - bx1) * (by2 - by1) > 0.92:
            continue                                 # a speck, or "the whole crop": not a real answer
        if not _close(targets[i][0], new, W, H):
            continue                                 # a jump to something else, not a correction: keep the first look
        sharp[i] = (new, targets[i][1])
    return sharp


def _close(old, new, W, H):
    """Is `new` a correction of `old` (same thing, nearby) rather than a different thing?"""
    ow, oh = (old[2] - old[0]) * W, (old[3] - old[1]) * H
    dx = abs((old[0] + old[2]) - (new[0] + new[2])) / 2 * W
    dy = abs((old[1] + old[3]) - (new[1] + new[3])) / 2 * H
    return dx <= ow * 0.6 + 30 and dy <= oh * 0.6 + 30


# ── Snapping to what's really on screen ──────────────────────────────────────

SNAP_INK = 60       # how different from the background a pixel must be to count as content
SNAP_GAP = 5        # rows of background that separate two lines or blocks

def snap(img, box):
    """Tighten a rough box (0..1 of img) onto the real content under it: the text lines, button or panel.
    Looks at the pixels only (free and instant). Returns the rough box if nothing clearly fits."""
    import numpy as np
    W, H = img.size
    x1, y1, x2, y2 = box[0] * W, box[1] * H, box[2] * W, box[3] * H
    bw, bh = x2 - x1, y2 - y1
    mx, my = max(16.0, bw * 0.15), max(18.0, bh * 0.45)
    rx1, ry1, rx2, ry2 = int(max(0, x1 - mx)), int(max(0, y1 - my)), int(min(W, x2 + mx)), int(min(H, y2 + my))
    if rx2 - rx1 < 8 or ry2 - ry1 < 8:
        return box
    a = np.asarray(img.crop((rx1, ry1, rx2, ry2)), dtype=np.int16)
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(edge, axis=0)
    ink = np.abs(a - bg).sum(axis=2) > SNAP_INK                 # anything that isn't background
    rows = ink.sum(axis=1) > max(1, ink.shape[1] * 0.004)
    # Bands of content rows (text lines, a button, a panel), split by gaps of background.
    bands, start, gap = [], None, 0
    for i, on in enumerate(rows):
        if on:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > SNAP_GAP:                                  # a real gap between lines/blocks
                bands.append((start, i - gap + 1))
                start, gap = None, 0
    if start is not None:
        bands.append((start, len(rows) - gap))
    if not bands:
        return box
    oy1, oy2 = y1 - ry1, y2 - ry1                               # the rough box, in this crop
    keep = [b for b in bands if min(b[1], oy2) - max(b[0], oy1) >= 0.5 * (b[1] - b[0])]
    if not keep:                                                # nothing mostly inside: the band nearest the middle
        mid = (oy1 + oy2) / 2
        keep = [min(bands, key=lambda b: abs((b[0] + b[1]) / 2 - mid))]
    ny1, ny2 = min(b[0] for b in keep), max(b[1] for b in keep)
    xs = np.nonzero(ink[ny1:ny2].sum(axis=0) > 0)[0]
    if not len(xs):
        return box
    nx1, nx2 = xs[0], xs[-1] + 1
    new = ((rx1 + nx1) / W, (ry1 + ny1) / H, (rx1 + nx2) / W, (ry1 + ny2) / H)
    nw, nh = (new[2] - new[0]) * W, (new[3] - new[1]) * H
    if nw < 6 or nh < 6 or nw * nh > bw * bh * 4 or nw * nh < bw * bh * 0.08 or not _close(box, new, W, H):
        return box
    return new


def locate(img, question, title=""):
    """First look: (spoken answer, rough boxes as [((x1, y1, x2, y2) 0..1 of img, label)])."""
    from ..brain import _parse_json
    square, sx, sy = _squared(img)
    raw = svc.brain.see(POINT.format(title=title or "unknown"), question, data_url(square), max_tokens=500)
    out = _parse_json(raw)
    if not isinstance(out, dict) or "answer" not in out:
        return raw.strip(), []                       # plain text answer: still fine, just nothing to outline
    return str(out["answer"]).strip(), _boxes(out.get("highlights"), sx, sy)


def _highlight_later(img, monitor, boxes, question, seconds):
    """Sharpen the boxes with a zoomed-in second look, then draw them (the answer is already being spoken).
    Skipped when the vision model's per-minute allowance is low, so it never costs you your next question."""
    sharp = boxes
    model = (svc.config["ai"].get("vision_models") or ["qwen/qwen3.8-27b"])[0]
    if svc.brain.budget(model) >= REFINE_COST:
        try:
            sharp = refine(img, boxes, question)
        except Exception:
            log.debug("Refining highlights failed", exc_info=True)
    else:
        log.info("Highlights: skipped the zoomed look to save the AI allowance")
    try:
        sharp = [(snap(img, b), label) for b, label in sharp]
    except Exception:
        log.debug("Snapping highlights failed", exc_info=True)
    svc.overlay.highlight(monitor, sharp, seconds=seconds)


def _capture():
    img, title = grab()
    return data_url(img), title


@action("explain_screen", "Look at the user's screen and answer a question about it: explain an error, summarize "
        "a page, read something out, say what's going on.", "question?: str")
def explain_screen(question=""):
    import threading
    question = (question or "").strip() or "What's on my screen? Explain the important part."
    svc.state.update(thinking=True)
    img, title, monitor = grab(with_box=True, full=True)
    try:
        answer, boxes = locate(img, question, title)
    except BrainUnavailable as e:
        raise ActionError(str(e))
    if not answer:
        raise ActionError("I couldn't read the screen just now.")
    if boxes and svc.overlay and hasattr(svc.overlay, "highlight") and (svc.config.get("appearance") or {}).get(
            "screen_highlights", True):
        threading.Thread(target=_highlight_later, args=(img, monitor, boxes, question, max(8.0, len(answer) / 12.0)),
                         name="highlight", daemon=True).start()
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
