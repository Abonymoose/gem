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
        self.boxes = []
        for (x1, y1, x2, y2), label in boxes:
            r = QRectF(x1 * g.width(), y1 * g.height(), (x2 - x1) * g.width(), (y2 - y1) * g.height())
            self.boxes.append((r.adjusted(-PAD, -PAD, PAD, PAD), label))
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
            self.boxes = []
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
