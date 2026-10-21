"""Answer card content, drawn inside the island when it opens up.

Every kind of card has a height function and a paint function. Live pieces
(timer rings, typing dots, equalizer bars) animate because the overlay
repaints the card every frame while it's visible.
"""
import datetime
import math
import os
import time

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QConicalGradient, QFont, QFontMetrics, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPolygonF, QRadialGradient)

from . import theme as T


F_LABEL = T.font(11, QFont.DemiBold)
F_LABEL.setLetterSpacing(QFont.AbsoluteSpacing, 1.3)
F_YOU = T.font(13, italic=True)
F_BODY = T.font(15)
F_SMALL = T.font(13)
F_ROW = T.font(14)
F_TITLE = T.font(17, QFont.DemiBold)
F_BIG = T.font(40, QFont.Light)
F_HUGE = T.font(36, QFont.Normal)
F_TIME = T.font(28, QFont.DemiBold)
F_RING = T.font(15, QFont.DemiBold)
_PICK_TITLE_H = 22


def _wrap_height(font, text, width, max_lines=None):
    fm = QFontMetrics(font)
    h = fm.boundingRect(QRect(0, 0, int(width), 100000), Qt.TextWordWrap, text).height()
    if max_lines:
        h = min(h, fm.lineSpacing() * max_lines)
    return h


def _clock(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%I:%M %p").lstrip("0")


def _countdown(sec):
    sec = max(0, int(math.ceil(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


# ── Icons ────────────────────────────────────────────────────────────────────

def _cloud_path(x, y, s):
    path = QPainterPath()
    path.setFillRule(Qt.WindingFill)      # overlapping puffs merge instead of cutting holes
    path.addEllipse(QRectF(x + s * 0.05, y + s * 0.38, s * 0.42, s * 0.42))
    path.addEllipse(QRectF(x + s * 0.22, y + s * 0.18, s * 0.5, s * 0.5))
    path.addEllipse(QRectF(x + s * 0.5, y + s * 0.36, s * 0.42, s * 0.42))
    path.addRoundedRect(QRectF(x + s * 0.12, y + s * 0.55, s * 0.72, s * 0.25), s * 0.12, s * 0.12)
    return path.simplified()


def draw_weather_icon(p, x, y, s, code, is_day=True, t=0.0):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    sunny = code in (0, 1)
    cloudy = code in (2, 3, 45, 48) or code >= 51
    if code in (0, 1, 2):
        cx, cy = (x + s * 0.5, y + s * 0.45) if code != 2 else (x + s * 0.36, y + s * 0.34)
        r = s * (0.24 if code != 2 else 0.19)
        if is_day:
            p.setPen(QPen(QColor(251, 191, 36, 220), s * 0.045, Qt.SolidLine, Qt.RoundCap))
            for k in range(8):
                a = math.radians(k * 45 + t * 20)
                p.drawLine(QPointF(cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35),
                           QPointF(cx + math.cos(a) * r * 1.7, cy + math.sin(a) * r * 1.7))
            g = QRadialGradient(QPointF(cx - r * 0.3, cy - r * 0.3), r * 1.4)
            g.setColorAt(0, QColor(254, 240, 138))
            g.setColorAt(1, QColor(245, 158, 11))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(cx, cy), r, r)
        else:
            moon = QPainterPath()
            moon.addEllipse(QPointF(cx, cy), r * 1.1, r * 1.1)
            cut = QPainterPath()
            cut.addEllipse(QPointF(cx + r * 0.55, cy - r * 0.35), r * 0.95, r * 0.95)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(226, 232, 240))
            p.drawPath(moon.subtracted(cut))
    if cloudy or code == 2:
        cs = s * (0.9 if code != 2 else 0.78)
        cxo = x + (s - cs) / 2 + (s * 0.08 if code == 2 else 0)
        cyo = y + (s - cs) / 2 - s * 0.06 + (s * 0.08 if code == 2 else 0)
        g = QLinearGradient(QPointF(cxo, cyo), QPointF(cxo, cyo + cs))
        dark = code >= 61 or code in (3, 95, 96, 99)
        g.setColorAt(0, QColor(241, 245, 249) if not dark else QColor(203, 213, 225))
        g.setColorAt(1, QColor(148, 163, 184) if not dark else QColor(100, 116, 139))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPath(_cloud_path(cxo, cyo, cs))
        base = cyo + cs * 0.82
        if 51 <= code <= 67 or 80 <= code <= 82:
            p.setPen(QPen(QColor(96, 165, 250), s * 0.045, Qt.SolidLine, Qt.RoundCap))
            for k in range(3):
                ox = cxo + cs * (0.3 + 0.2 * k)
                off = ((t * 1.6 + k * 0.3) % 1.0) * s * 0.08
                p.drawLine(QPointF(ox, base + off), QPointF(ox - s * 0.05, base + s * 0.12 + off))
        elif 71 <= code <= 77 or code in (85, 86):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255))
            for k in range(3):
                p.drawEllipse(QPointF(cxo + cs * (0.3 + 0.2 * k), base + s * 0.08 + (k % 2) * s * 0.05), s * 0.035, s * 0.035)
        elif code >= 95:
            bolt = QPolygonF([QPointF(cxo + cs * 0.52, base - s * 0.02), QPointF(cxo + cs * 0.4, base + s * 0.12),
                              QPointF(cxo + cs * 0.5, base + s * 0.12), QPointF(cxo + cs * 0.42, base + s * 0.24),
                              QPointF(cxo + cs * 0.62, base + s * 0.06), QPointF(cxo + cs * 0.52, base + s * 0.06)])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(250, 204, 21))
            p.drawPolygon(bolt)
        elif code in (45, 48):
            p.setPen(QPen(QColor(203, 213, 225, 200), s * 0.04, Qt.SolidLine, Qt.RoundCap))
            for k in range(2):
                yy = base + s * (0.06 + 0.08 * k)
                p.drawLine(QPointF(cxo + cs * 0.15, yy), QPointF(cxo + cs * 0.85, yy))
    p.restore()


def draw_bell(p, cx, cy, s, color):
    path = QPainterPath()
    path.moveTo(cx - s * 0.42, cy + s * 0.25)
    path.cubicTo(cx - s * 0.32, cy + s * 0.1, cx - s * 0.36, cy - s * 0.45, cx, cy - s * 0.45)
    path.cubicTo(cx + s * 0.36, cy - s * 0.45, cx + s * 0.32, cy + s * 0.1, cx + s * 0.42, cy + s * 0.25)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPath(path)
    p.drawEllipse(QPointF(cx, cy + s * 0.36), s * 0.1, s * 0.1)
    p.drawEllipse(QPointF(cx, cy - s * 0.5), s * 0.06, s * 0.06)


def draw_speaker(p, cx, cy, s, color, muted=False):
    poly = QPolygonF([QPointF(cx - s * 0.45, cy - s * 0.15), QPointF(cx - s * 0.25, cy - s * 0.15),
                      QPointF(cx, cy - s * 0.4), QPointF(cx, cy + s * 0.4),
                      QPointF(cx - s * 0.25, cy + s * 0.15), QPointF(cx - s * 0.45, cy + s * 0.15)])
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPolygon(poly)
    pen = QPen(color, s * 0.08, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if muted:
        p.drawLine(QPointF(cx + s * 0.15, cy - s * 0.15), QPointF(cx + s * 0.45, cy + s * 0.15))
        p.drawLine(QPointF(cx + s * 0.45, cy - s * 0.15), QPointF(cx + s * 0.15, cy + s * 0.15))
    else:
        for k, r in enumerate((0.22, 0.4)):
            p.drawArc(QRectF(cx - s * r, cy - s * r, s * r * 2, s * r * 2), -45 * 16, 90 * 16)


def draw_check(p, x, y, s, done):
    rect = QRectF(x, y, s, s)
    if done:
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        g.setColorAt(0, QColor(167, 139, 250))
        g.setColorAt(1, QColor(124, 58, 237))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(255, 255, 255), s * 0.13, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath(QPointF(x + s * 0.28, y + s * 0.52))
        path.lineTo(x + s * 0.44, y + s * 0.68)
        path.lineTo(x + s * 0.73, y + s * 0.34)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    else:
        p.setPen(QPen(T.alpha(T.SOFT, 0.6), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(rect.adjusted(0.75, 0.75, -0.75, -0.75))


def draw_ring(p, cx, cy, r, progress, width, colors=None, track=None):
    rect = QRectF(cx - r, cy - r, r * 2, r * 2)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(track or T.alpha(T.SOFT, 0.14), width, Qt.SolidLine, Qt.RoundCap))
    p.drawEllipse(rect)
    if progress <= 0:
        return
    g = QConicalGradient(QPointF(cx, cy), 90)
    stops = colors or [QColor(196, 160, 240), QColor(139, 92, 246), QColor(236, 72, 153)]
    for i, c in enumerate(stops):
        g.setColorAt(i / max(1, len(stops) - 1), c)
    p.setPen(QPen(g, width, Qt.SolidLine, Qt.RoundCap))
    p.drawArc(rect, 90 * 16, int(-min(1.0, progress) * 360 * 16))


# ── Card ─────────────────────────────────────────────────────────────────────

LABELS = {"weather": "WEATHER", "timer": "TIMER", "focus": "FOCUS", "alarm": "ALARM", "timers": "TIMERS & REMINDERS",
          "todo": "TO-DO", "music": "NOW PLAYING", "system": "THIS PC", "schedule": "SCHEDULE", "volume": "VOLUME",
          "clock": "", "briefing": "", "alert": "", "image": "SCREENSHOT", "confirm": "CONFIRM", "text": "",
          "pending": "", "web": "FROM THE WEB", "routine": "ROUTINE", "draft": "DRAFT", "calc": "",
          "clips": "CLIPBOARD", "reading": "READING ALOUD", "habit": "",
          "world": "WORLD CLOCK", "countdown": "COUNTDOWN", "usage": "SCREEN TIME",
          "screen": "ON YOUR SCREEN", "speed": "INTERNET SPEED", "picks": "PICKS", "tidy": "DOWNLOADS TIDIED",
          "voice": "VOICE TRAINING", "people": "VOICES I KNOW", "color": "UNDER YOUR MOUSE", "files": "FILES",
          "trivia": "TRIVIA"}


class CardContent:
    """What goes inside the island when it opens up: your words, a label and the card body."""

    def __init__(self):
        self.you = ""
        self.text = ""
        self.card = None
        self._image = None
        self.t = 0.0

    # ── Content ──────────────────────────────────────────────────────────────

    def set_content(self, you=None, text=None, card=None):
        if you is not None:
            self.you = you
            if text is None and card is None:
                self.text, self.card = "", {"kind": "pending"}
        if text is not None:
            self.text = text
        if card is not None or text is not None:
            self.card = card or {"kind": "text"}
        if self.card and self.card.get("kind") == "image":
            path = self.card.get("path")
            self._image = QImage(path) if path and os.path.exists(path) else None

    @property
    def kind(self):
        return (self.card or {}).get("kind", "text")

    def _label(self):
        c = self.card or {}
        if c.get("header"):
            return c["header"].upper()
        label = LABELS.get(self.kind, "")
        if self.kind == "weather" and c.get("city"):
            label += " · " + c["city"].upper()
        if self.kind == "schedule" and c.get("title"):
            label += " · " + c["title"].upper()
        if self.kind == "volume" and c.get("app"):
            label = c["app"].upper() + " VOLUME"
        if self.kind == "alarm":
            label = (c.get("title") or "Alarm").upper()
        if self.kind == "focus" and c.get("phase") == "break":
            label = "BREAK"
        if self.kind == "usage" and c.get("period"):
            label += " · " + c["period"].upper()
        if self.kind == "habit" and c.get("habit"):
            label = c["habit"].upper() + (" · %d-DAY STREAK" % c["streak"] if c.get("streak", 0) > 1 else "")
        if self.kind == "draft" and c.get("title"):
            label = c["title"].upper()
        if self.kind == "routine" and c.get("name"):
            label += " · " + c["name"].upper()
        if self.kind == "picks" and c.get("title"):
            label = c["title"].upper()
        if self.kind == "files" and c.get("total"):
            label += " · %d FOUND" % c["total"]
        if self.kind == "trivia":
            label = "TRIVIA · %s" % (c.get("topic") or "").upper()
            if not c.get("done"):
                label += " · %d OF %d" % (c.get("number", 1), c.get("total", 5))
        if self.kind == "voice":
            who = c.get("person")
            if c.get("done"):
                label = "%s'S VOICE LEARNED" % who.upper() if who else "VOICE LOCK ON"
            else:
                label = "%s · %d OF %d" % ("LEARNING %s'S VOICE" % who.upper() if who else "VOICE TRAINING",
                                          c.get("step", 0) + 1, c.get("total", 5))
        return label

    def height(self, w):
        """Height of the content when laid out `w` pixels wide."""
        h = 0
        if self.you:
            h += _wrap_height(F_YOU, "“%s”" % self.you, w, max_lines=2) + 10
        if self._label():
            h += QFontMetrics(F_LABEL).height() + 10
        return h + self._body_height(w)

    def _body_height(self, w):
        c, k = self.card or {}, self.kind
        if k == "pending":
            return 18
        if k == "text":
            return _wrap_height(F_BODY, self.text, w) if self.text else 0
        if k == "weather":
            return 92
        if k in ("timer", "focus"):
            return 76
        if k == "alarm":
            return 56
        if k == "timers":
            return 32 * min(6, len(c.get("items") or [])) or 24
        if k == "todo":
            n = min(7, len(c.get("items") or []))
            return (30 * n or 24) + (20 if len(c.get("items") or []) > 7 else 0)
        if k == "music":
            return 64
        if k == "system":
            return 96
        if k == "schedule":
            return 32 * max(1, min(6, len(c.get("rows") or [])))
        if k == "volume":
            return 36
        if k == "clock":
            return 72
        if k == "briefing":
            rows = c.get("rows") or []
            return QFontMetrics(F_TITLE).height() + 10 + sum(_wrap_height(F_ROW, r["text"], w - 34) + 12 for r in rows)
        if k == "alert":
            return max(48, QFontMetrics(F_TITLE).height() + 6 + _wrap_height(F_SMALL, c.get("message", ""), w - 64))
        if k == "image":
            if self._image is None or self._image.isNull():
                return 24
            return min(220, int(w * self._image.height() / max(1, self._image.width()))) + 26
        if k == "confirm":
            return _wrap_height(F_BODY, self.text, w) + 40
        if k == "calc":
            return 66
        if k == "world":
            return 40 * max(1, min(6, len(c.get("rows") or [])))
        if k == "countdown":
            return 70
        if k in ("usage", "tidy"):
            return 54 + 30 * min(6, len(c.get("rows") or []))
        if k == "speed":
            return 80
        if k == "color":
            return 60
        if k == "files":
            return 46 * min(5, len(c.get("rows") or [])) - 4
        if k == "trivia":
            if c.get("done"):
                return 64 + _wrap_height(F_SMALL, self.text, w)
            top = 24 if c.get("last_ok") is not None else 0
            return top + _wrap_height(F_TITLE, c.get("question", ""), w) + 10 + 30 * len(c.get("options") or []) + 22
        if k == "people":
            return 34 * (min(6, len(c.get("rows") or [])) + (1 if c.get("me") else 0))
        if k == "voice":
            if c.get("done"):
                return _wrap_height(F_BODY, self.text, w) + 30
            return (_wrap_height(F_SMALL, self.text, w) + 8 + _wrap_height(F_TITLE, "“%s”" % c.get("phrase", ""), w)
                    + 14 + 18)
        if k == "picks":
            return sum(_PICK_TITLE_H + 2 + _wrap_height(F_SMALL, r.get("why", ""), w - 38) + 14
                       for r in (c.get("rows") or [])[:3]) - 4
        if k == "clips":
            return 28 * max(1, min(8, len(c.get("items") or [])))
        if k == "reading":
            return _wrap_height(F_BODY, c.get("note", ""), w)
        if k == "habit":
            return 92
        if k == "draft":
            return _wrap_height(F_BODY, c.get("note", ""), w - 16) + 14 + _wrap_height(F_SMALL, self.text, w)
        if k == "web":
            return _wrap_height(F_BODY, self.text, w) + (36 if c.get("sources") else 0)
        if k == "routine":
            return 28 * min(8, len(c.get("steps") or [])) + _wrap_height(F_SMALL, self.text, w) + 10
        return _wrap_height(F_BODY, self.text, w)

    # ── Painting ─────────────────────────────────────────────────────────────

    def paint(self, p, x, y, w, t):
        self.t = t
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        if self.you:
            p.setFont(F_YOU)
            p.setPen(T.TEXT_FAINT)
            hy = _wrap_height(F_YOU, "“%s”" % self.you, w, max_lines=2)
            p.drawText(QRectF(x, y, w, hy), Qt.TextWordWrap, "“%s”" % self.you)
            y += hy + 10
        label = self._label()
        if label:
            p.setFont(F_LABEL)
            p.setPen(T.LAVENDER)
            lh = QFontMetrics(F_LABEL).height()
            p.drawText(QRectF(x, y, w, lh), Qt.AlignLeft | Qt.AlignVCenter, label)
            y += lh + 10
        getattr(self, "_paint_" + self.kind, self._paint_text)(p, x, y, w)

    def _paint_text(self, p, x, y, w):
        p.setFont(F_BODY)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y, w, _wrap_height(F_BODY, self.text, w) + 4), Qt.TextWordWrap, self.text)

    def _paint_pending(self, p, x, y, w):
        p.setPen(Qt.NoPen)
        for k in range(3):
            a = 0.35 + 0.65 * max(0.0, math.sin(self.t * 5 - k * 0.7))
            p.setBrush(T.alpha(T.SOFT, a))
            p.drawEllipse(QPointF(x + 6 + k * 14, y + 9), 4, 4)

    def _paint_weather(self, p, x, y, w):
        c = self.card
        draw_weather_icon(p, x - 4, y, 80, int(c.get("code", 0)), c.get("is_day", True), self.t)
        tx = x + 92
        if c.get("when") in ("today", "tomorrow"):
            p.setFont(F_BIG)
            p.setPen(T.TEXT)
            p.drawText(QRectF(tx, y - 4, w - 92, 50), Qt.AlignLeft | Qt.AlignVCenter,
                       "%d° / %d°" % (c.get("high", 0), c.get("low", 0)))
            sub = "%s · %s" % (c.get("when", "").capitalize(), c.get("desc", "").capitalize())
            detail = "%d%% chance of rain" % (c.get("rain") or 0)
        else:
            p.setFont(F_BIG)
            p.setPen(T.TEXT)
            p.drawText(QRectF(tx, y - 4, w - 92, 50), Qt.AlignLeft | Qt.AlignVCenter, "%d°" % c.get("temp", 0))
            sub = c.get("desc", "").capitalize()
            detail = "Feels like %d° · H %d° L %d° · Rain %d%%" % (
                c.get("feels", 0), c.get("high", 0), c.get("low", 0), c.get("rain") or 0)
        p.setFont(F_ROW)
        p.setPen(T.TEXT)
        p.drawText(QRectF(tx, y + 48, w - 92, 20), Qt.AlignLeft | Qt.AlignVCenter, sub)
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(tx, y + 70, w - 92, 20), Qt.AlignLeft | Qt.AlignVCenter, detail)

    def _paint_timer(self, p, x, y, w):
        c = self.card
        left = max(0.0, c.get("ends_at", 0) - time.time())
        total = max(1.0, float(c.get("total") or 1))
        draw_ring(p, x + 36, y + 38, 32, left / total, 6)
        p.setFont(F_RING)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y + 6, 72, 64), Qt.AlignCenter, _countdown(left))
        title = c.get("label") or ("Focus session" if self.kind == "focus" else "Timer")
        if self.kind == "focus" and c.get("phase") == "break":
            title = "Break"
        p.setFont(F_TITLE)
        p.drawText(QRectF(x + 92, y + 10, w - 92, 26), Qt.AlignLeft | Qt.AlignVCenter, title.capitalize())
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x + 92, y + 38, w - 92, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   "Done at %s" % _clock(c.get("ends_at", time.time())) if left > 0 else "Done")

    _paint_focus = _paint_timer

    def _paint_alarm(self, p, x, y, w):
        c = self.card
        g = QLinearGradient(QPointF(x, y), QPointF(x + 52, y + 52))
        g.setColorAt(0, QColor(167, 139, 250))
        g.setColorAt(1, QColor(124, 58, 237))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(x, y + 2, 52, 52), 14, 14)
        draw_bell(p, x + 26, y + 28, 26, QColor(255, 255, 255))
        p.setFont(F_TIME)
        p.setPen(T.TEXT)
        when = c.get("at", time.time())
        day = datetime.datetime.fromtimestamp(when).date()
        today = datetime.date.today()
        p.drawText(QRectF(x + 68, y - 2, w - 68, 34), Qt.AlignLeft | Qt.AlignVCenter, _clock(when))
        dayname = "Today" if day == today else "Tomorrow" if day == today + datetime.timedelta(days=1) \
            else datetime.datetime.fromtimestamp(when).strftime("%A")
        sub = dayname + (" · " + c["subtitle"] if c.get("subtitle") else "")
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x + 68, y + 32, w - 68, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(F_SMALL).elidedText(sub, Qt.ElideRight, int(w - 68)))

    def _paint_timers(self, p, x, y, w):
        items = (self.card.get("items") or [])[:6]
        if not items:
            p.setFont(F_ROW)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x, y, w, 24), Qt.AlignLeft | Qt.AlignVCenter, "Nothing scheduled.")
            return
        for i, it in enumerate(items):
            yy = y + i * 32
            if it["kind"] == "timer":
                left = max(0.0, it["at"] - time.time())
                draw_ring(p, x + 11, yy + 13, 9, left / max(1.0, it.get("total") or 1), 3)
                right = _countdown(left)
                name = (it.get("label") or "Timer").capitalize()
            else:
                draw_bell(p, x + 11, yy + 13, 16, T.SOFT)
                right = _clock(it["at"])
                if datetime.datetime.fromtimestamp(it["at"]).date() != datetime.date.today():
                    right = datetime.datetime.fromtimestamp(it["at"]).strftime("%a ") + right
                name = (it.get("message") or it.get("label") or it["kind"]).capitalize()
            p.setFont(F_ROW)
            p.setPen(T.TEXT)
            p.drawText(QRectF(x + 32, yy, w - 140, 26), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(F_ROW).elidedText(name, Qt.ElideRight, int(w - 140)))
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x + w - 108, yy, 108, 26), Qt.AlignRight | Qt.AlignVCenter, right)

    def _paint_todo(self, p, x, y, w):
        items = self.card.get("items") or []
        if not items:
            p.setFont(F_ROW)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x, y, w, 24), Qt.AlignLeft | Qt.AlignVCenter, "All clear.")
            return
        fm = QFontMetrics(F_ROW)
        for i, it in enumerate(items[:7]):
            yy = y + i * 30
            draw_check(p, x, yy + 3, 18, it.get("done"))
            p.setFont(F_ROW)
            p.setPen(T.TEXT_FAINT if it.get("done") else T.TEXT)
            f = QFont(F_ROW)
            f.setStrikeOut(bool(it.get("done")))
            p.setFont(f)
            p.drawText(QRectF(x + 30, yy, w - 30, 24), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(it["text"], Qt.ElideRight, int(w - 30)))
        if len(items) > 7:
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x + 30, y + 7 * 30, w, 18), Qt.AlignLeft, "+%d more" % (len(items) - 7))

    def _paint_music(self, p, x, y, w):
        c = self.card
        g = QLinearGradient(QPointF(x, y), QPointF(x + 60, y + 60))
        g.setColorAt(0, QColor(236, 72, 153))
        g.setColorAt(1, QColor(124, 58, 237))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(x, y, 60, 60), 14, 14)
        p.setFont(T.font(30, family="Segoe UI Symbol"))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x, y, 60, 60), Qt.AlignCenter, "♫")
        p.setFont(F_TITLE)
        p.setPen(T.TEXT)
        fm = QFontMetrics(F_TITLE)
        p.drawText(QRectF(x + 76, y + 4, w - 120, 26), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(c.get("title", ""), Qt.ElideRight, int(w - 120)))
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x + 76, y + 32, w - 120, 22), Qt.AlignLeft | Qt.AlignVCenter, c.get("artist", ""))
        if c.get("playing", True):
            for k in range(4):
                hgt = 6 + 14 * abs(math.sin(self.t * (4 + k * 1.3) + k))
                p.setPen(Qt.NoPen)
                p.setBrush(T.alpha(T.SOFT, 0.85))
                p.drawRoundedRect(QRectF(x + w - 34 + k * 8, y + 40 - hgt, 4, hgt), 2, 2)

    def _paint_system(self, p, x, y, w):
        c = self.card
        gauges = [("CPU", c.get("cpu")), ("RAM", c.get("ram")), ("Disk", c.get("disk"))]
        if c.get("battery") is not None:
            gauges.append(("Battery", c["battery"]))
        n = len(gauges)
        cw = w / n
        for i, (name, val) in enumerate(gauges):
            cx = x + cw * i + cw / 2
            hot = val is not None and val >= 85 and name != "Battery"
            colors = [QColor(251, 146, 60), QColor(239, 68, 68)] if hot else None
            draw_ring(p, cx, y + 34, 30, (val or 0) / 100.0, 6, colors)
            p.setFont(F_RING)
            p.setPen(T.TEXT)
            p.drawText(QRectF(cx - 30, y + 4, 60, 60), Qt.AlignCenter, "%d%%" % (val or 0))
            p.setFont(F_SMALL)
            p.setPen(T.LAVENDER if name.lower() == str(c.get("highlight", "")).lower() else T.TEXT_DIM)
            p.drawText(QRectF(cx - 40, y + 72, 80, 20), Qt.AlignCenter, name)

    def _paint_schedule(self, p, x, y, w):
        rows = (self.card.get("rows") or [])[:6]
        if not rows:
            p.setFont(F_ROW)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x, y, w, 24), Qt.AlignLeft | Qt.AlignVCenter, "Nothing scheduled.")
            return
        for i, r in enumerate(rows):
            yy = y + i * 32
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.VIOLET if r.get("next") else T.SOFT, 0.9 if r.get("next") else 0.35))
            p.drawRoundedRect(QRectF(x, yy + 4, 4, 20), 2, 2)
            p.setFont(T.font(14, QFont.DemiBold))
            p.setPen(T.TEXT)
            p.drawText(QRectF(x + 14, yy, 96, 28), Qt.AlignLeft | Qt.AlignVCenter, r.get("time", ""))
            p.setFont(F_ROW)
            p.drawText(QRectF(x + 112, yy, w - 112, 28), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(F_ROW).elidedText(r.get("name", "").capitalize(), Qt.ElideRight, int(w - 112)))

    def _paint_volume(self, p, x, y, w):
        c = self.card
        muted = c.get("muted")
        level = 0 if muted else c.get("level", 0)
        if c.get("icon") == "sun":
            cx, cy = x + 14, y + 18
            p.setPen(QPen(T.TEXT, 1.8, Qt.SolidLine, Qt.RoundCap))
            for i in range(8):
                ang = math.radians(45 * i)
                p.drawLine(QPointF(cx + math.cos(ang) * 8.5, cy + math.sin(ang) * 8.5),
                           QPointF(cx + math.cos(ang) * 12, cy + math.sin(ang) * 12))
            p.setPen(Qt.NoPen)
            p.setBrush(T.TEXT)
            p.drawEllipse(QPointF(cx, cy), 5.5, 5.5)
        else:
            draw_speaker(p, x + 14, y + 18, 26, T.TEXT, muted)
        bar = QRectF(x + 40, y + 13, w - 100, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(T.alpha(T.SOFT, 0.14))
        p.drawRoundedRect(bar, 5, 5)
        if level:
            g = QLinearGradient(bar.topLeft(), bar.topRight())
            g.setColorAt(0, QColor(196, 160, 240))
            g.setColorAt(1, QColor(139, 92, 246))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * level / 100.0, bar.height()), 5, 5)
        p.setFont(F_RING)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x + w - 52, y, 52, 36), Qt.AlignRight | Qt.AlignVCenter, "Muted" if muted else "%d" % level)

    def _paint_clock(self, p, x, y, w):
        c = self.card
        p.setFont(T.font(40, QFont.Light))
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y - 4, w, 48), Qt.AlignLeft | Qt.AlignVCenter, c.get("time", ""))
        p.setFont(F_ROW)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x, y + 46, w, 24), Qt.AlignLeft | Qt.AlignVCenter, c.get("date", ""))

    def _paint_briefing(self, p, x, y, w):
        c = self.card
        p.setFont(F_TITLE)
        p.setPen(T.TEXT)
        th = QFontMetrics(F_TITLE).height()
        p.drawText(QRectF(x, y, w, th), Qt.AlignLeft | Qt.AlignVCenter, c.get("greeting", ""))
        y += th + 10
        for r in c.get("rows") or []:
            h = _wrap_height(F_ROW, r["text"], w - 34)
            icon = r.get("icon")
            if icon == "weather":
                draw_weather_icon(p, x - 2, y - 3, 26, int(r.get("code", 1)), True, self.t)
            elif icon == "todo":
                draw_check(p, x + 3, y + 1, 16, False)
            else:
                draw_bell(p, x + 11, y + 10, 16, T.SOFT) if icon == "bell" else None
                if icon == "dot":
                    p.setPen(Qt.NoPen)
                    p.setBrush(T.alpha(T.LAVENDER, 0.9))
                    p.drawEllipse(QRectF(x + 7, y + 7, 7, 7))
                if icon == "class":
                    p.setPen(Qt.NoPen)
                    p.setBrush(T.alpha(T.VIOLET, 0.9))
                    p.drawRoundedRect(QRectF(x + 8, y + 2, 4, 18), 2, 2)
            p.setFont(F_ROW)
            p.setPen(T.TEXT)
            p.drawText(QRectF(x + 34, y, w - 34, h + 2), Qt.TextWordWrap, r["text"])
            y += h + 12

    def _paint_alert(self, p, x, y, w):
        c = self.card
        pulse = 0.5 + 0.5 * math.sin(self.t * 6)
        g = QRadialGradient(QPointF(x + 24, y + 24), 30)
        g.setColorAt(0, T.alpha(T.VIOLET, 0.55 + 0.35 * pulse))
        g.setColorAt(1, T.alpha(T.VIOLET, 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(x + 24, y + 24), 30, 30)
        draw_bell(p, x + 24, y + 24, 28, QColor(255, 255, 255))
        th = QFontMetrics(F_TITLE).height()
        p.setFont(F_TITLE)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x + 64, y, w - 64, th), Qt.AlignLeft | Qt.AlignVCenter, c.get("title", "Reminder"))
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        msg = c.get("message", "")
        p.drawText(QRectF(x + 64, y + th + 6, w - 64, _wrap_height(F_SMALL, msg, w - 64) + 4), Qt.TextWordWrap, msg)

    def _paint_image(self, p, x, y, w):
        if self._image is None or self._image.isNull():
            self._paint_text(p, x, y, w)
            return
        h = min(220, int(w * self._image.height() / max(1, self._image.width())))
        iw = min(w, h * self._image.width() / max(1, self._image.height()))     # keep the aspect (QR codes stay square)
        target = QRectF(x + (w - iw) / 2, y, iw, h)
        path = QPainterPath()
        path.addRoundedRect(target, 12, 12)
        p.save()
        p.setClipPath(path)
        p.drawImage(target, self._image)
        p.restore()
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        note = self.card.get("note") or "Saved to Desktop · copied"
        p.drawText(QRectF(x, y + h + 6, w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(F_SMALL).elidedText(note, Qt.ElideRight, int(w)))

    def _paint_confirm(self, p, x, y, w):
        self._paint_text(p, x, y, w)
        th = _wrap_height(F_BODY, self.text, w)
        chips = [("Yes", True), ("No", False)]
        cx = x
        for name, primary in chips:
            r = QRectF(cx, y + th + 10, 64, 26)
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.VIOLET, 0.85) if primary else T.alpha(T.SOFT, 0.15))
            p.drawRoundedRect(r, 13, 13)
            p.setFont(T.font(13, QFont.DemiBold))
            p.setPen(T.TEXT)
            p.drawText(r, Qt.AlignCenter, name)
            cx += 74
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_FAINT)
        p.drawText(QRectF(cx + 6, y + th + 10, w - cx, 26), Qt.AlignLeft | Qt.AlignVCenter, "Just say yes or no")

    def _paint_web(self, p, x, y, w):
        self._paint_text(p, x, y, w)
        sources = self.card.get("sources") or []
        if not sources:
            return
        cy = y + _wrap_height(F_BODY, self.text, w) + 12
        cx = x
        p.setFont(T.font(11, QFont.DemiBold))
        fm = QFontMetrics(p.font())
        for s in sources:
            tw = fm.horizontalAdvance(s) + 20
            if cx + tw > x + w:
                break
            r = QRectF(cx, cy, tw, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.SOFT, 0.14))
            p.drawRoundedRect(r, 11, 11)
            p.setPen(T.TEXT_DIM)
            p.drawText(r, Qt.AlignCenter, s)
            cx += tw + 8

    def _paint_routine(self, p, x, y, w):
        steps = (self.card.get("steps") or [])[:8]
        for i, st in enumerate(steps):
            yy = y + i * 28
            if st.get("ok"):
                draw_check(p, x, yy + 3, 18, True)
            else:
                p.setPen(QPen(QColor(248, 113, 113), 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x + 5, yy + 8), QPointF(x + 13, yy + 16))
                p.drawLine(QPointF(x + 13, yy + 8), QPointF(x + 5, yy + 16))
            p.setFont(F_ROW)
            p.setPen(T.TEXT if st.get("ok") else T.TEXT_DIM)
            p.drawText(QRectF(x + 30, yy, w - 30, 24), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(F_ROW).elidedText(st.get("text", "").capitalize(), Qt.ElideRight, int(w - 30)))
        ty = y + len(steps) * 28 + 6
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x, ty, w, _wrap_height(F_SMALL, self.text, w) + 4), Qt.TextWordWrap, self.text)

    def _paint_draft(self, p, x, y, w):
        note = self.card.get("note", "")
        nh = _wrap_height(F_BODY, note, w - 16)
        p.setPen(Qt.NoPen)
        p.setBrush(T.alpha(T.VIOLET, 0.9))
        p.drawRoundedRect(QRectF(x, y + 2, 3, nh - 2), 1.5, 1.5)
        p.setFont(F_BODY)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x + 16, y, w - 16, nh + 4), Qt.TextWordWrap, note)
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x, y + nh + 14, w, _wrap_height(F_SMALL, self.text, w) + 4), Qt.TextWordWrap, self.text)

    def _paint_calc(self, p, x, y, w):
        c = self.card
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x, y, w, 20), Qt.AlignLeft | Qt.AlignVCenter, c.get("expression", ""))
        p.setFont(T.font(34, QFont.Light))
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y + 20, w, 44), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(p.font()).elidedText("= " + c.get("result", ""), Qt.ElideRight, int(w)))

    def _paint_clips(self, p, x, y, w):
        for i, it in enumerate((self.card.get("items") or [])[:8]):
            yy = y + i * 28
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.SOFT, 0.16))
            p.drawEllipse(QRectF(x, yy + 3, 20, 20))
            p.setFont(T.font(11, QFont.DemiBold))
            p.setPen(T.SOFT)
            p.drawText(QRectF(x, yy + 3, 20, 20), Qt.AlignCenter, str(it["n"]))
            p.setFont(F_ROW)
            p.setPen(T.TEXT)
            p.drawText(QRectF(x + 30, yy, w - 30, 26), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(F_ROW).elidedText(it["text"], Qt.ElideRight, int(w - 30)))

    def _paint_reading(self, p, x, y, w):
        note = self.card.get("note", "")
        p.setFont(F_BODY)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y, w, _wrap_height(F_BODY, note, w) + 4), Qt.TextWordWrap, note)

    def _paint_habit(self, p, x, y, w):
        c = self.card
        p.setFont(T.font(40, QFont.Light))
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y - 4, 110, 50), Qt.AlignLeft | Qt.AlignVCenter, str(c.get("today", 0)))
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x, y + 46, 130, 20), Qt.AlignLeft | Qt.AlignVCenter, "%s today" % c.get("unit", ""))
        days = c.get("days") or []
        top = max([v for _, v in days] + [1])
        bx, bw, gap, hmax = x + 150, 22, 12, 56
        for i, (label, v) in enumerate(days):
            h = max(3, hmax * v / top) if v else 3
            r = QRectF(bx + i * (bw + gap), y + 6 + hmax - h, bw, h)
            today = i == len(days) - 1
            if v:
                g = QLinearGradient(r.bottomLeft(), r.topLeft())
                g.setColorAt(0, QColor(124, 58, 237))
                g.setColorAt(1, QColor(196, 160, 240) if today else QColor(139, 92, 246))
                p.setBrush(g)
            else:
                p.setBrush(T.alpha(T.SOFT, 0.14))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 4, 4)
            p.setFont(T.font(11, QFont.DemiBold if today else QFont.Normal))
            p.setPen(T.TEXT if today else T.TEXT_FAINT)
            p.drawText(QRectF(r.left() - 4, y + 66, bw + 8, 18), Qt.AlignCenter, label)

    def _paint_world(self, p, x, y, w):
        for i, r in enumerate((self.card.get("rows") or [])[:6]):
            yy = y + i * 40
            place = "Your time" if r.get("place") == "Here" else r.get("place", "")
            p.setFont(F_TITLE)
            p.setPen(T.TEXT)
            p.drawText(QRectF(x, yy, w * 0.55, 22), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(F_TITLE).elidedText(place, Qt.ElideRight, int(w * 0.55)))
            sub = " · ".join(v for v in (r.get("day") if r.get("day") not in ("", "Today") else "", r.get("offset", ""))
                             if v and v != "same time")
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x, yy + 20, w * 0.6, 18), Qt.AlignLeft | Qt.AlignVCenter, sub)
            p.setFont(T.font(24, QFont.Light))
            p.setPen(T.TEXT)
            p.drawText(QRectF(x + w * 0.45, yy, w * 0.55, 38), Qt.AlignRight | Qt.AlignVCenter, r.get("time", ""))

    def _paint_countdown(self, p, x, y, w):
        c = self.card
        days = c.get("days", 0)
        p.setFont(T.font(44, QFont.Light))
        p.setPen(T.TEXT)
        num = c.get("label", "") if c.get("time_only") else ("Today" if days == 0 else str(days))
        nw = QFontMetrics(p.font()).horizontalAdvance(num)
        p.drawText(QRectF(x, y - 6, nw + 4, 56), Qt.AlignLeft | Qt.AlignVCenter, num)
        if days:
            p.setFont(F_TITLE)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x + nw + 10, y + 18, 80, 26), Qt.AlignLeft | Qt.AlignVCenter, "day" if days == 1 else "days")
        label = "" if c.get("time_only") else c.get("label", "")
        p.setFont(F_TITLE)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x + w * 0.42, y + 4, w * 0.58, 24), Qt.AlignRight | Qt.AlignVCenter,
                   QFontMetrics(F_TITLE).elidedText(label[:1].upper() + label[1:], Qt.ElideRight, int(w * 0.58)))
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x + w * 0.42, y + 30, w * 0.58, 20), Qt.AlignRight | Qt.AlignVCenter, c.get("date", ""))

    def _paint_usage(self, p, x, y, w, total_key="total"):
        c = self.card
        p.setFont(T.font(30, QFont.Light))
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y - 4, w, 42), Qt.AlignLeft | Qt.AlignVCenter, str(c.get(total_key, "")))
        rows = (c.get("rows") or [])[:6]
        top = max([r["secs"] for r in rows] + [1])
        for i, r in enumerate(rows):
            yy = y + 50 + i * 30
            p.setFont(F_ROW)
            p.setPen(T.TEXT)
            p.drawText(QRectF(x, yy, 120, 24), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(F_ROW).elidedText(r["name"], Qt.ElideRight, 116))
            bar = QRectF(x + 126, yy + 8, (w - 206) * r["secs"] / top, 8)
            g = QLinearGradient(bar.topLeft(), bar.topRight())
            g.setColorAt(0, QColor(139, 92, 246))
            g.setColorAt(1, QColor(196, 160, 240))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(bar, 4, 4)
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            if self.kind == "tidy":
                value = "%d" % r["secs"]
            else:
                m = int(r["secs"] // 60)
                value = ("%dh %dm" % (m // 60, m % 60)) if m >= 60 else ("%dm" % m if m else "<1m")
            p.drawText(QRectF(x + w - 74, yy, 74, 24), Qt.AlignRight | Qt.AlignVCenter, value)

    def _paint_tidy(self, p, x, y, w):
        n = self.card.get("total", 0)
        self.card.setdefault("total_text", "%d file%s moved" % (n, "" if n == 1 else "s"))
        self._paint_usage(p, x, y, w, total_key="total_text")

    def _paint_speed(self, p, x, y, w):
        c = self.card

        def mbps(v):
            return "%.0f" % v if v >= 10 else "%.1f" % v

        p.setFont(T.font(40, QFont.Light))
        p.setPen(T.TEXT)
        num = mbps(c.get("down", 0))
        nw = QFontMetrics(p.font()).horizontalAdvance(num)
        p.drawText(QRectF(x, y - 6, nw + 4, 54), Qt.AlignLeft | Qt.AlignVCenter, num)
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x + nw + 8, y + 20, 110, 20), Qt.AlignLeft | Qt.AlignVCenter, "Mbps down")
        sx = x + w * 0.56
        for i, (name, value) in enumerate([("Upload", "%s Mbps" % mbps(c.get("up", 0))),
                                           ("Ping", "%d ms" % c.get("ping", 0))]):
            yy = y + 2 + i * 24
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(sx, yy, w * 0.2, 20), Qt.AlignLeft | Qt.AlignVCenter, name)
            p.setFont(T.font(14, QFont.DemiBold))
            p.setPen(T.TEXT)
            p.drawText(QRectF(sx, yy, x + w - sx, 20), Qt.AlignRight | Qt.AlignVCenter, value)
        p.setFont(F_SMALL)
        p.setPen(T.LAVENDER)
        p.drawText(QRectF(x, y + 56, w, 20), Qt.AlignLeft | Qt.AlignVCenter, c.get("verdict", ""))

    def _paint_files(self, p, x, y, w):
        for i, r in enumerate((self.card.get("rows") or [])[:5]):
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.VIOLET, 0.85) if i == 0 else T.alpha(T.SOFT, 0.16))
            p.drawRoundedRect(QRectF(x, y + 4, 26, 30), 6, 6)
            ext = os.path.splitext(r["name"])[1][1:4].upper() or "?"
            p.setFont(T.font(8, QFont.DemiBold))
            p.setPen(T.TEXT)
            p.drawText(QRectF(x, y + 4, 26, 30), Qt.AlignCenter, ext)
            p.setFont(T.font(14, QFont.DemiBold))
            p.drawText(QRectF(x + 38, y, w - 38, 22), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(r["name"], Qt.ElideMiddle, int(w - 38)))
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x + 38, y + 20, w - 38, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       "%s · %s · %s" % (r.get("folder", ""), r.get("when", ""), r.get("size", "")))
            y += 46

    def _paint_trivia(self, p, x, y, w):
        c = self.card
        if c.get("done"):
            p.setFont(T.font(36, QFont.Light))
            p.setPen(T.TEXT)
            p.drawText(QRectF(x, y - 4, w, 50), Qt.AlignLeft | Qt.AlignVCenter, "%d / %d" % (c.get("score", 0),
                                                                                         c.get("total", 5)))
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x, y + 56, w, _wrap_height(F_SMALL, self.text, w) + 4), Qt.TextWordWrap, self.text)
            return
        if c.get("last_ok") is not None:
            ok = c["last_ok"]
            p.setFont(T.font(12, QFont.DemiBold))
            p.setPen(QColor(52, 211, 153) if ok else QColor(244, 114, 182))
            p.drawText(QRectF(x, y, w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       ("✓  Correct" if ok else "✗  Not quite") + "   ·   score %d" % c.get("score", 0))
            y += 24
        q = c.get("question", "")
        qh = _wrap_height(F_TITLE, q, w)
        p.setFont(F_TITLE)
        p.setPen(T.TEXT)
        p.drawText(QRectF(x, y, w, qh + 2), Qt.TextWordWrap, q)
        y += qh + 10
        for i, opt in enumerate(c.get("options") or []):
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.VIOLET, 0.8))
            p.drawEllipse(QRectF(x, y + 2, 22, 22))
            p.setFont(T.font(11, QFont.DemiBold))
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(x, y + 2, 22, 22), Qt.AlignCenter, "ABCD"[i])
            p.setFont(F_ROW)
            p.setPen(T.TEXT)
            p.drawText(QRectF(x + 34, y, w - 34, 26), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(F_ROW).elidedText(opt, Qt.ElideRight, int(w - 34)))
            y += 30
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_FAINT)
        p.drawText(QRectF(x, y + 2, w, 18), Qt.AlignLeft | Qt.AlignVCenter, "Say A, B, C or D · skip · stop")

    def _paint_color(self, p, x, y, w):
        c = self.card
        r, g, b = (c.get("rgb") or [0, 0, 0])[:3]
        p.setPen(QPen(T.alpha(T.SOFT, 0.35), 1))
        p.setBrush(QColor(r, g, b))
        p.drawRoundedRect(QRectF(x, y + 2, 56, 56), 14, 14)
        p.setFont(T.font(24, QFont.DemiBold))
        p.setPen(T.TEXT)
        p.drawText(QRectF(x + 72, y, w - 72, 34), Qt.AlignLeft | Qt.AlignVCenter, c.get("hex", ""))
        p.setFont(F_SMALL)
        p.setPen(T.TEXT_DIM)
        p.drawText(QRectF(x + 72, y + 34, w - 72, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   "%s · rgb(%d, %d, %d) · copied" % (c.get("name", "").capitalize(), r, g, b))

    def _paint_people(self, p, x, y, w):
        c = self.card
        rows = ([{"name": "You", "relation": "", "state": "voice lock on" if c.get("locked") else "voice lock off",
                  "me": True}] if c.get("me") else []) + (c.get("rows") or [])[:6]
        for r in rows:
            blocked = r["state"].startswith("blocked")
            # Avatar: initial in a circle, violet for you, dim for blocked people.
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.VIOLET, 0.9) if r.get("me") else T.alpha(T.SOFT, 0.12 if blocked else 0.22))
            p.drawEllipse(QRectF(x, y + 2, 26, 26))
            p.setFont(T.font(12, QFont.DemiBold))
            p.setPen(T.TEXT_DIM if blocked else T.TEXT)
            p.drawText(QRectF(x, y + 2, 26, 26), Qt.AlignCenter, r["name"][:1].upper())
            p.setFont(T.font(14, QFont.DemiBold))
            p.setPen(T.TEXT_DIM if blocked else T.TEXT)
            name = r["name"] + ("  · %s" % r["relation"] if r.get("relation") else "")
            p.drawText(QRectF(x + 38, y, w * 0.6, 30), Qt.AlignLeft | Qt.AlignVCenter, name)
            p.setFont(F_SMALL)
            p.setPen(T.alpha(QColor(244, 114, 182), 0.95) if blocked else T.LAVENDER)
            p.drawText(QRectF(x + w * 0.45, y, w * 0.55, 30), Qt.AlignRight | Qt.AlignVCenter, r["state"].capitalize())
            y += 34

    def _paint_voice(self, p, x, y, w):
        c = self.card
        total, step = c.get("total", 5), c.get("step", 0)
        if c.get("done"):
            self._paint_text(p, x, y, w)
            y += _wrap_height(F_BODY, self.text, w) + 12
        else:
            sh = _wrap_height(F_SMALL, self.text, w)
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(x, y, w, sh + 2), Qt.TextWordWrap, self.text)
            y += sh + 8
            phrase = "“%s”" % c.get("phrase", "")
            ph = _wrap_height(F_TITLE, phrase, w)
            p.setFont(F_TITLE)
            p.setPen(T.TEXT)
            p.drawText(QRectF(x, y, w, ph + 2), Qt.TextWordWrap, phrase)
            y += ph + 14
        # Progress: one dot per line, the current one pulsing.
        pulse = 0.55 + 0.45 * math.sin(self.t * 5)
        for i in range(total):
            done = i < step
            current = i == step and not c.get("done")
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.VIOLET, 0.95) if done else T.alpha(T.LAVENDER, pulse) if current
                       else T.alpha(T.SOFT, 0.18))
            p.drawEllipse(QRectF(x + i * 16, y + 4, 9, 9))
        if not c.get("done"):
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_FAINT)
            p.drawText(QRectF(x + total * 16 + 8, y, w - total * 16 - 8, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       c.get("hint", ""))

    def _paint_picks(self, p, x, y, w):
        for i, r in enumerate((self.card.get("rows") or [])[:3]):
            # Numbered dot
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(T.VIOLET, 0.85))
            p.drawEllipse(QRectF(x, y + 1, 22, 22))
            p.setFont(T.font(11, QFont.DemiBold))
            p.setPen(QColor(255, 255, 255))
            p.drawText(QRectF(x, y + 1, 22, 22), Qt.AlignCenter, str(i + 1))
            tx, tw = x + 38, w - 38
            chip = "Installed" if r.get("installed") else (r.get("kind") or "").capitalize()
            p.setFont(T.font(11, QFont.DemiBold))
            cw = QFontMetrics(p.font()).horizontalAdvance(chip) + 16 if chip else 0
            p.setFont(T.font(15, QFont.DemiBold))
            p.setPen(T.TEXT)
            p.drawText(QRectF(tx, y, tw - cw - 8, _PICK_TITLE_H), Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(p.font()).elidedText(r.get("title", ""), Qt.ElideRight, int(tw - cw - 8)))
            if chip:
                cr = QRectF(x + w - cw, y + 1, cw, 20)
                p.setPen(Qt.NoPen)
                p.setBrush(T.alpha(T.VIOLET, 0.35) if r.get("installed") else T.alpha(T.SOFT, 0.14))
                p.drawRoundedRect(cr, 10, 10)
                p.setFont(T.font(11, QFont.DemiBold))
                p.setPen(T.TEXT if r.get("installed") else T.TEXT_DIM)
                p.drawText(cr, Qt.AlignCenter, chip)
            why = r.get("why", "")
            wh = _wrap_height(F_SMALL, why, tw)
            p.setFont(F_SMALL)
            p.setPen(T.TEXT_DIM)
            p.drawText(QRectF(tx, y + _PICK_TITLE_H + 2, tw, wh + 2), Qt.TextWordWrap, why)
            y += _PICK_TITLE_H + 2 + wh + 14
