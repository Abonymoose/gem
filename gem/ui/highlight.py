"""Screen highlights: a see-through layer that outlines what Gem is talking about and dims the rest.

Purely visual: it never takes clicks, keys or focus (everything goes straight through to your apps).
Two uses:
  - highlights: after "what's this error?" / "where's the save button?", glowing outlines on the spots
    the answer is about, fading away after a few seconds;
  - spotlight: "spotlight this window" dims everything except the window you're working in, following you.
"""
import ctypes
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme as T

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x20, 0x80000, 0x80, 0x08000000
_u32 = ctypes.windll.user32
_u32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_u32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]

DIM = 0.42          # how dark the rest of the screen gets
PAD = 10            # breathing room around a highlighted spot (logical px)


def _screen_for(phys):
    """The QScreen showing a monitor given in physical pixels (left, top, right, bottom)."""
    w, h = phys[2] - phys[0], phys[3] - phys[1]
    best, best_d = None, None
    for s in QGuiApplication.screens():
        g, dpr = s.geometry(), s.devicePixelRatio()
        d = abs(g.width() * dpr - w) + abs(g.height() * dpr - h) + abs(g.x() * dpr - phys[0]) * 0.01
        if best is None or d < best_d:
            best, best_d = s, d
    return best or QGuiApplication.primaryScreen()


class HighlightOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.boxes = []                 # [(QRectF in this window, label)]
        self.callouts = []              # autofill: [{"rect", "label", "text", "why", "n"}]
        self.until = 0.0
        self.alpha = 0.0
        self.t0 = time.monotonic()
        self.spot = False               # spotlight mode
        self.spot_rect = None
        self.hidden_for = 0.0           # briefly hidden while Gem takes a screenshot
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    # ── Window plumbing ──────────────────────────────────────────────────────

    def _clickthrough(self):
        hwnd = int(self.winId())
        style = _u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        _u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                            style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)

    def _cover(self, screen):
        if self.geometry() != screen.geometry():
            self.setGeometry(screen.geometry())
        if not self.isVisible():
            self.show()
            self._clickthrough()
        if not self.timer.isActive():
            self.timer.start(16)

    # ── Public (Qt thread) ───────────────────────────────────────────────────

    def show_highlights(self, phys_monitor, boxes, seconds=9.0):
        """boxes: [(x1, y1, x2, y2) as 0..1 of the monitor, label]."""
        screen = _screen_for(phys_monitor)
        g = screen.geometry()
        self.boxes, self.callouts = [], []
        for (x1, y1, x2, y2), label in boxes:
            r = QRectF(x1 * g.width(), y1 * g.height(), (x2 - x1) * g.width(), (y2 - y1) * g.height())
            self.boxes.append((r.adjusted(-PAD, -PAD, PAD, PAD), label))
        self.until = time.monotonic() + seconds
        self.t0 = time.monotonic()
        self._cover(screen)
        self.update()

    def show_callouts(self, phys_monitor, items, seconds=40.0):
        """Autofill: items are dicts with box (0..1 of the monitor), label, text, why, n, blank (write the answer
        inside the box) and dark (the screen under it is dark)."""
        screen = _screen_for(phys_monitor)
        g = screen.geometry()
        self.boxes, self.callouts = [], []
        for n, it in enumerate(items, 1):
            x1, y1, x2, y2 = it["box"]
            r = QRectF(x1 * g.width(), y1 * g.height(), (x2 - x1) * g.width(), (y2 - y1) * g.height())
            self.callouts.append({"rect": r.adjusted(-4, -4, 4, 4), "inner": r, "label": it.get("label", ""),
                                  "text": it.get("text", ""), "why": it.get("why", ""), "n": it.get("n", n),
                                  "blank": bool(it.get("blank")), "dark": bool(it.get("dark"))})
        self.until = time.monotonic() + seconds
        self.t0 = time.monotonic()
        self._cover(screen)
        self.update()

    def clear(self):
        self.until = 0.0                # fades out

    def set_spotlight(self, on):
        self.spot = bool(on)
        if on:
            self._cover(QGuiApplication.primaryScreen())
            self.t0 = time.monotonic()
        self.update()

    def hide_briefly(self, seconds):
        self.hidden_for = time.monotonic() + seconds
        self.setWindowOpacity(0.0)

    # ── Frame ────────────────────────────────────────────────────────────────

    def _follow_window(self):
        """Spotlight: where the window in front is, in this screen's coordinates."""
        from ..winapi import foreground_window, monitor_rect_physical, window_class, window_pid, window_rect_physical
        import os
        hwnd = foreground_window()
        if not hwnd or window_pid(hwnd) == os.getpid() or window_class(hwnd) in (
                "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return None
        mon = monitor_rect_physical(hwnd)
        if not mon:
            return None
        screen = _screen_for(mon)
        if self.geometry() != screen.geometry():
            self.setGeometry(screen.geometry())
        dpr = screen.devicePixelRatio()
        l, t, r, b = window_rect_physical(hwnd)
        return QRectF((l - mon[0]) / dpr, (t - mon[1]) / dpr, (r - l) / dpr, (b - t) / dpr)

    def _tick(self):
        now = time.monotonic()
        if self.hidden_for and now >= self.hidden_for:
            self.hidden_for = 0.0
            self.setWindowOpacity(1.0)
        showing = self.spot or now < self.until
        target = 1.0 if showing else 0.0
        self.alpha += (target - self.alpha) * min(1.0, 0.016 * (9 if showing else 6))
        if self.spot:
            try:
                self.spot_rect = self._follow_window()
            except Exception:
                self.spot_rect = None
        if not showing and self.alpha < 0.01:
            self.alpha = 0.0
            self.boxes, self.callouts = [], []
            self.timer.stop()
            self.hide()
            return
        self.update()

    def paintEvent(self, _):
        if self.alpha <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        full = QPainterPath()
        full.addRect(QRectF(self.rect()))
        holes = QPainterPath()
        if self.callouts and time.monotonic() < self.until + 1:
            for c in self.callouts:
                one = QPainterPath()
                one.addRoundedRect(c["rect"], 6, 6)
                holes = holes.united(one)
            # A light dim only: you still need to read the sheet around the suggestions.
            p.fillPath(full.subtracted(holes), QColor(6, 4, 14, int(255 * 0.16 * self.alpha)))
            self._callouts(p)
            p.end()
            return
        rects = [r for r, _ in self.boxes] if self.boxes and time.monotonic() < self.until + 1 else []
        if self.spot and self.spot_rect is not None and not rects:
            rects = [self.spot_rect]
        for r in rects:
            one = QPainterPath()
            one.addRoundedRect(r, 14, 14)
            holes = holes.united(one)               # overlapping spots stay fully lit
        if not self.spot and not rects:
            p.end()
            return
        p.fillPath(full.subtracted(holes), QColor(6, 4, 14, int(255 * DIM * self.alpha)))
        if self.boxes and rects and rects[0] is not self.spot_rect:
            self._outlines(p)
        p.end()

    def _callouts(self, p):
        """Each spot to fill: a numbered outline, and a card beside it with what goes there."""
        a = self.alpha
        t = time.monotonic() - self.t0
        pulse = 0.8 + 0.2 * math.sin(t * 3.0)
        mono = QFont("Cascadia Mono", 13, QFont.Bold)
        if not QFontMetrics(mono).inFont("="):
            mono = QFont("Consolas", 13, QFont.Bold)
        f_label, f_why = T.font(10, QFont.DemiBold), T.font(10)
        placed = []
        W, H = self.width(), self.height()
        for c in self.callouts:
            r, n = c["rect"], c["n"]
            # Outline on the spot itself.
            for i in range(3):
                p.setPen(QPen(T.alpha(QColor(139, 92, 246), 0.18 * pulse * a * (1 - i / 3)), 3 + i * 4))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r, 6, 6)
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0.0, T.alpha(QColor(196, 160, 240), a))
            g.setColorAt(1.0, T.alpha(QColor(236, 72, 153), a))
            p.setPen(QPen(g, 2.2))
            p.drawRoundedRect(r, 6, 6)
            if c.get("blank"):
                self._ghost(p, c, mono, a)
                self._badge(p, r, n, a)
                continue
            # No blank to write in: a card beside it with what to put there, and why.
            fm_t, fm_l, fm_w = QFontMetrics(mono), QFontMetrics(f_label), QFontMetrics(f_why)
            head = "%d  ·  %s" % (n, c["label"]) if c["label"] else str(n)
            cw = max(fm_t.horizontalAdvance(c["text"]), fm_l.horizontalAdvance(head),
                     fm_w.horizontalAdvance(c["why"]) if c["why"] else 0) + 40
            cw = min(cw, 460)
            ch = 14 + fm_l.height() + 4 + fm_t.height() + (4 + fm_w.height() if c["why"] else 0) + 12
            right = r.right() + 18 + cw <= W - 8
            x = r.right() + 18 if right else max(8, r.left() - 18 - cw)
            y = min(max(8, r.center().y() - ch / 2), H - ch - 8)
            card = QRectF(x, y, cw, ch)
            for other in placed:                                    # don't stack cards on top of each other
                if card.intersects(other):
                    card.moveTop(other.bottom() + 8)
            placed.append(card)
            # Connector from the spot to its card.
            sx = r.right() if right else r.left()
            p.setPen(QPen(T.alpha(QColor(167, 139, 250), 0.85 * a), 1.6))
            p.drawLine(QPointF(sx, r.center().y()), QPointF(card.left() if right else card.right(), card.center().y()))
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(QColor(18, 12, 30), 0.95 * a))
            p.drawRoundedRect(card, 12, 12)
            p.setPen(QPen(T.alpha(QColor(167, 139, 250), 0.85 * a), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(card, 12, 12)
            yy = card.top() + 12
            p.setFont(f_label)
            p.setPen(T.alpha(QColor(167, 139, 250), a))
            p.drawText(QRectF(card.left() + 14, yy, cw - 28, fm_l.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fm_l.elidedText(head, Qt.ElideRight, int(cw - 28)))
            yy += fm_l.height() + 4
            p.setFont(mono)
            p.setPen(T.alpha(QColor(244, 240, 251), a))
            p.drawText(QRectF(card.left() + 14, yy, cw - 28, fm_t.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       fm_t.elidedText(c["text"], Qt.ElideRight, int(cw - 28)))
            yy += fm_t.height() + 4
            if c["why"]:
                p.setFont(f_why)
                p.setPen(T.alpha(QColor(190, 180, 210), a))
                p.drawText(QRectF(card.left() + 14, yy, cw - 28, fm_w.height()), Qt.AlignLeft | Qt.AlignVCenter,
                           fm_w.elidedText(c["why"], Qt.ElideRight, int(cw - 28)))
            self._badge(p, r, n, a)

    def _badge(self, p, r, n, a):
        """The suggestion's number, on the spot's corner (matches "copy number 2")."""
        p.setPen(Qt.NoPen)
        p.setBrush(T.alpha(QColor(139, 92, 246), a))
        p.drawEllipse(QPointF(r.left(), r.top()), 9, 9)
        p.setFont(T.font(9, QFont.Bold))
        p.setPen(T.alpha(QColor(255, 255, 255), a))
        p.drawText(QRectF(r.left() - 9, r.top() - 9, 18, 18), Qt.AlignCenter, str(n))

    def _ghost(self, p, c, mono, a):
        """Write the answer inside the blank, like it's already filled in (only drawn, never typed)."""
        inner = c["inner"]
        text = c["text"]
        size = int(max(11, min(34, inner.height() * 0.6)))              # pixels, in proportion to the blank
        font = QFont(mono)
        font.setPixelSize(size)
        fm = QFontMetrics(font)
        while fm.horizontalAdvance(text) > inner.width() - 12 and size > 11:   # shrink to fit the blank
            size -= 1
            font.setPixelSize(size)
            fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(text) + 12
        area = QRectF(inner.left(), inner.top(), max(inner.width(), tw), inner.height())
        # A soft wash so the answer reads cleanly over underlines or gridlines.
        wash = QColor(30, 22, 48) if c.get("dark") else QColor(250, 247, 255)
        p.setPen(Qt.NoPen)
        p.setBrush(T.alpha(wash, 0.88 * a))
        p.drawRoundedRect(area.adjusted(1, 1, -1, -1), 5, 5)
        ink = QColor(221, 205, 255) if c.get("dark") else QColor(109, 40, 217)
        p.setFont(font)
        p.setPen(T.alpha(ink, a))
        p.drawText(area.adjusted(6, 0, -6, 0), Qt.AlignLeft | Qt.AlignVCenter, text)
        if c.get("why"):
            # The working, small, just under the blank.
            f = T.font(9)
            fw = QFontMetrics(f)
            tip = QRectF(area.left(), area.bottom() + 4, min(fw.horizontalAdvance(c["why"]) + 14, 420), fw.height() + 6)
            if tip.bottom() > self.height() - 4:
                tip.moveBottom(area.top() - 4)
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(QColor(18, 12, 30), 0.88 * a))
            p.drawRoundedRect(tip, 8, 8)
            p.setFont(f)
            p.setPen(T.alpha(QColor(225, 215, 245), a))
            p.drawText(tip, Qt.AlignCenter, fw.elidedText(c["why"], Qt.ElideRight, int(tip.width() - 10)))

    def _outlines(self, p):
        t = time.monotonic() - self.t0
        pulse = 0.75 + 0.25 * math.sin(t * 3.2)
        for r, label in self.boxes:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0.0, T.alpha(QColor(196, 160, 240), self.alpha))
            g.setColorAt(0.5, T.alpha(QColor(139, 92, 246), self.alpha))
            g.setColorAt(1.0, T.alpha(QColor(236, 72, 153), self.alpha))
            for i in range(4):                                      # soft outer glow
                p.setPen(QPen(T.alpha(QColor(139, 92, 246), 0.16 * pulse * self.alpha * (1 - i / 4)), 3 + i * 4))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r, 14, 14)
            p.setPen(QPen(g, 2.6))
            p.drawRoundedRect(r, 14, 14)
            if label:
                f = T.font(12, QFont.DemiBold)
                fm = QFontMetrics(f)
                tw = fm.horizontalAdvance(label) + 22
                pill = QRectF(r.left(), r.top() - 30, tw, 24)
                if pill.top() < 4:                                  # no room above: put it below
                    pill.moveTop(r.bottom() + 6)
                p.setPen(Qt.NoPen)
                p.setBrush(T.alpha(QColor(18, 12, 30), 0.92 * self.alpha))
                p.drawRoundedRect(pill, 12, 12)
                p.setPen(QPen(T.alpha(QColor(167, 139, 250), 0.8 * self.alpha), 1))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(pill, 12, 12)
                p.setFont(f)
                p.setPen(T.alpha(QColor(244, 240, 251), self.alpha))
                p.drawText(pill, Qt.AlignCenter, label)
