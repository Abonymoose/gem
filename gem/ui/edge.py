"""The screen-edge glow shown while you hold Caps Lock to talk.

Four thin click-through strips along the screen edges each paint their slice
of one continuous, slowly rotating gradient, which is far cheaper than a
full-screen transparent window.
"""
import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QConicalGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import theme as T

THICK = 44


class _Strip(QWidget):
    def __init__(self, owner):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.owner = owner

    def paintEvent(self, _):
        o = self.owner
        if o.intensity <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(-(self.x() - o.screen_rect.x()), -(self.y() - o.screen_rect.y()))
        o.paint_glow(p)
        p.end()


class EdgeGlow:
    def __init__(self, screen):
        self.screen_rect = screen.geometry()
        self.intensity = 0.0
        self.target = 0.0
        self.level = 0.0
        self.angle = 0.0
        self.strips = [_Strip(self) for _ in range(4)]
        self._place()

    def _place(self):
        r = self.screen_rect
        geo = [QRect(r.x(), r.y(), r.width(), THICK), QRect(r.x(), r.bottom() - THICK + 1, r.width(), THICK),
               QRect(r.x(), r.y() + THICK, THICK, r.height() - THICK * 2),
               QRect(r.right() - THICK + 1, r.y() + THICK, THICK, r.height() - THICK * 2)]
        for s, g in zip(self.strips, geo):
            s.setGeometry(g)

    def set_active(self, on):
        self.target = 1.0 if on else 0.0

    @property
    def visible(self):
        return self.intensity > 0.01 or self.target > 0

    def step(self, dt, level):
        rate = 9.0 if self.target > self.intensity else 4.5
        self.intensity += (self.target - self.intensity) * (1 - math.exp(-rate * dt))
        self.level += (level - self.level) * (1 - math.exp(-12 * dt))
        self.angle = (self.angle + dt * 50) % 360
        showing = self.intensity > 0.01
        for s in self.strips:
            if showing and not s.isVisible():
                s.show()
            elif not showing and s.isVisible():
                s.hide()
            elif showing:
                s.update()

    def paint_glow(self, p):
        r = QRectF(0, 0, self.screen_rect.width(), self.screen_rect.height())
        center = r.center()
        boost = 0.75 + 0.45 * min(1.0, self.level * 2.5)
        layers = 11
        for i in range(layers):
            k = i / (layers - 1)
            g = QConicalGradient(QPointF(center), self.angle)
            stops = T.GLOW + [T.GLOW[0]]
            for j, c in enumerate(stops):
                g.setColorAt(j / (len(stops) - 1), T.alpha(c, self.intensity * boost * (0.9 * (1 - k) ** 2.2)))
            width = 3 + k * 4
            inset = 1.5 + k * 3.6
            p.setPen(QPen(g, width))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(inset, inset, -inset, -inset), 14 + inset, 14 + inset)
