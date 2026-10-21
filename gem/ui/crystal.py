"""Gem's crystal eye, drawn with smooth anti-aliased vector graphics.

Crystal holds the animation state (eased each frame toward targets for the
current mood) and draw() paints it at any size, so the same code renders the
overlay, the tray icon and the dashboard logo.
"""
import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient

from . import theme as T

MOODS = ("launch", "idle", "listening", "muted", "thinking", "speaking", "sleeping", "gaming", "alert", "mini")

# mood -> (open, eye, glow, sparkle rate)
TARGETS = {
    "launch": (0.0, 1.0, 0.55, 0.0),
    "idle": (0.12, 1.0, 0.35, 0.4),
    "mini": (0.05, 0.75, 0.22, 0.0),
    "listening": (0.85, 1.0, 0.65, 2.2),
    "muted": (0.0, 0.0, 0.15, 0.0),
    "thinking": (0.38, 1.0, 0.5, 1.2),
    "speaking": (0.22, 1.0, 0.6, 0.8),
    "sleeping": (0.0, 0.0, 0.18, 0.3),
    "gaming": (0.05, 1.0, 0.35, 0.0),
    "alert": (0.5, 1.0, 0.85, 2.5),
}


def _ease(cur, target, rate, dt):
    return cur + (target - cur) * (1.0 - math.exp(-rate * dt))


def _star(cx, cy, s):
    path = QPainterPath()
    k = s * 0.22
    pts = [(0, -s), (k, -k), (s, 0), (k, k), (0, s), (-k, k), (-s, 0), (-k, -k)]
    path.moveTo(cx + pts[0][0], cy + pts[0][1])
    for x, y in pts[1:]:
        path.lineTo(cx + x, cy + y)
    path.closeSubpath()
    return path


class Crystal:
    def __init__(self):
        self.t = 0.0
        self.mood = "launch"
        self.open = 0.0
        self.eye = 0.0
        self.glow = 0.0
        self.level = 0.0
        self.pupil = 0.0
        self.look = [0.0, 0.0]
        self.look_target = [0.0, 0.0]
        self.next_look = 0.0
        self.blink = 0.0
        self.next_blink = 2.5
        self.assemble = 0.0
        self.burst_done = False
        self.sparkles = []

    # ── Animation ────────────────────────────────────────────────────────────

    def step(self, dt, mood, level=0.0):
        self.t += dt
        self.mood = mood
        o, e, g, rate = TARGETS.get(mood, TARGETS["idle"])
        self.level = _ease(self.level, level, 18, dt)
        if mood == "listening":
            o += self.level * 0.25
            g += self.level * 0.35
        if mood == "speaking":
            g += 0.15 * math.sin(self.t * 6.0) + 0.1 * math.sin(self.t * 9.7)
        if mood == "alert":
            g += 0.15 * math.sin(self.t * 8.0)
        self.open = _ease(self.open, o, 9, dt)
        self.eye = _ease(self.eye, e, 10, dt)
        self.glow = _ease(self.glow, g, 6, dt)
        self.pupil = _ease(self.pupil, self.level * 1.4 if mood == "listening" else 0.0, 14, dt)

        if mood == "launch":
            self.assemble = min(1.0, self.assemble + dt / 1.1)
            if self.assemble >= 1.0 and not self.burst_done:
                self.burst_done = True
                for _ in range(14):
                    self._spawn(burst=True)
        else:
            self.assemble = 1.0

        # Where the eye looks.
        if self.t >= self.next_look:
            if mood == "thinking":
                self.look_target = [random.choice((-0.6, 0.6)), -0.55]
                self.next_look = self.t + random.uniform(0.6, 1.2)
            elif mood in ("listening", "speaking"):
                self.look_target = [random.uniform(-0.15, 0.15), random.uniform(0.0, 0.2)]
                self.next_look = self.t + random.uniform(1.0, 2.0)
            else:
                ang, r = random.uniform(0, 2 * math.pi), random.uniform(0, 0.7)
                self.look_target = [math.cos(ang) * r, math.sin(ang) * r * 0.6]
                self.next_look = self.t + random.uniform(1.4, 3.2)
        self.look[0] = _ease(self.look[0], self.look_target[0], 7, dt)
        self.look[1] = _ease(self.look[1], self.look_target[1], 7, dt)

        # Blinking.
        if mood in ("idle", "listening", "thinking", "speaking", "mini", "gaming") and self.t >= self.next_blink:
            self.blink = 1.0
            self.next_blink = self.t + random.uniform(2.8, 6.0)
        self.blink = max(0.0, self.blink - dt / 0.16)

        # Sparkles.
        if rate and random.random() < rate * dt:
            self._spawn()
        for s in self.sparkles:
            s["life"] += dt
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
        self.sparkles = [s for s in self.sparkles if s["life"] < s["max"]]

    def _spawn(self, burst=False):
        ang = random.uniform(0, 2 * math.pi)
        r = random.uniform(0.9, 1.35) if not burst else random.uniform(0.3, 0.6)
        speed = random.uniform(0.05, 0.18) if not burst else random.uniform(0.6, 1.2)
        self.sparkles.append({"x": math.cos(ang) * r, "y": math.sin(ang) * r,
                              "vx": math.cos(ang) * speed, "vy": math.sin(ang) * speed - 0.05,
                              "life": 0.0, "max": random.uniform(0.7, 1.5), "size": random.uniform(0.07, 0.14),
                              "color": random.choice((T.HIGHLIGHT, T.SOFT, QColor(255, 255, 255)))})

    # ── Drawing ──────────────────────────────────────────────────────────────

    def draw(self, p, cx, cy, R, opacity=1.0):
        """Paint the crystal centred at (cx, cy) with radius R."""
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(opacity)
        self._draw_all(p, cx, cy, R)
        p.restore()

    def _draw_all(self, p, cx, cy, R):
        self._draw_glow(p, cx, cy, R)
        if self.mood == "speaking":
            self._draw_rings(p, cx, cy, R)
        if self.mood == "gaming":
            self._draw_scope(p, cx, cy, R)
        self._draw_shards(p, cx, cy, R)
        if self.eye * (1 - self.blink) > 0.06 and self.mood not in ("sleeping", "muted"):
            self._draw_eye(p, cx, cy, R)
        else:
            self._draw_closed_eye(p, cx, cy, R)
        if self.mood == "thinking":
            self._draw_orbit(p, cx, cy, R)
        self._draw_sparkles(p, cx, cy, R)

    def _draw_glow(self, p, cx, cy, R):
        g = max(0.0, self.glow)
        rad = R * 2.2
        grad = QRadialGradient(QPointF(cx, cy), rad)
        tint = T.mix(T.LAVENDER, QColor(220, 120, 220), 0.35 if self.mood == "speaking" else 0.0)
        grad.setColorAt(0.0, T.alpha(tint, 0.55 * g))
        grad.setColorAt(0.35, T.alpha(tint, 0.28 * g))
        grad.setColorAt(1.0, T.alpha(tint, 0.0))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawEllipse(QPointF(cx, cy), rad, rad)

    def _hex(self, cx, cy, r, rot=0.0):
        return QPolygonF([QPointF(cx + r * math.cos(math.radians(60 * i - 90 + rot)),
                                  cy + r * math.sin(math.radians(60 * i - 90 + rot))) for i in range(6)])

    def _draw_rings(self, p, cx, cy, R):
        for k in range(3):
            ph = (self.t * 0.8 + k / 3.0) % 1.0
            a = (1 - ph) * 0.55 * min(1.0, self.glow + 0.2)
            pen = QPen(T.alpha(T.SOFT, a), 1.4)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(self._hex(cx, cy, R * (1.05 + ph * 0.75), rot=ph * 12))

    def _draw_scope(self, p, cx, cy, R):
        ang = self.t * 25
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(T.alpha(T.IRIS, 0.8), 1.2))
        p.drawEllipse(QPointF(cx, cy), R * 1.45, R * 1.45)
        p.setPen(QPen(T.alpha(T.LAVENDER, 0.7), 1.0))
        p.drawEllipse(QPointF(cx, cy), R * 1.22, R * 1.22)
        for k in range(4):
            a = math.radians(ang + 90 * k)
            p.drawLine(QPointF(cx + math.cos(a) * R * 1.25, cy + math.sin(a) * R * 1.25),
                       QPointF(cx + math.cos(a) * R * 1.6, cy + math.sin(a) * R * 1.6))

    def _draw_shards(self, p, cx, cy, R):
        ease = 1 - (1 - self.assemble) ** 3
        verts = [QPointF(cx + R * math.cos(math.radians(60 * i - 90)), cy + R * math.sin(math.radians(60 * i - 90)))
                 for i in range(6)]
        sweep_speed = 0.55 if self.mood == "thinking" else 0.16
        sweep = (self.t * sweep_speed) % 1.8 - 0.4
        for i in range(6):
            v0, v1 = verts[i], verts[(i + 1) % 6]
            mx, my = (v0.x() + v1.x() + cx) / 3, (v0.y() + v1.y() + cy) / 3
            dx, dy = mx - cx, my - cy
            d = max(1e-3, math.hypot(dx, dy))
            push = self.open * R * 0.26 + (1 - ease) * R * 1.7
            ox, oy = dx / d * push, dy / d * push
            p.save()
            p.translate(ox, oy)
            if ease < 1:
                p.translate(mx, my)
                p.rotate((1 - ease) * (70 if i % 2 else -70))
                p.translate(-mx, -my)
            tri = QPolygonF([v0, v1, QPointF(cx, cy)])
            outer = QPointF((v0.x() + v1.x()) / 2, (v0.y() + v1.y()) / 2)
            grad = QLinearGradient(outer, QPointF(cx, cy))
            # Light from the top left: facets facing it are brighter.
            lit = 0.5 + 0.5 * ((dx / d) * -0.55 + (dy / d) * -0.83)
            grad.setColorAt(0.0, T.mix(QColor(52, 32, 92), QColor(118, 80, 182), lit))
            grad.setColorAt(0.55, T.mix(QColor(34, 22, 60), QColor(74, 48, 124), lit))
            grad.setColorAt(1.0, QColor(20, 13, 36))
            p.setOpacity(p.opacity() * min(1.0, 0.2 + ease))
            p.setBrush(grad)
            p.setPen(QPen(T.alpha(T.LAVENDER, 0.78), max(1.0, R * 0.045), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolygon(tri)
            # Glass gleam sweeping left to right across the facets.
            u = (mx - (cx - R)) / (2 * R)
            g = math.exp(-((u - sweep) ** 2) / 0.012)
            if g > 0.02:
                p.setPen(Qt.NoPen)
                p.setBrush(T.alpha(QColor(255, 255, 255), 0.22 * g))
                p.drawPolygon(tri)
            # Bright outer edge and a facet reflection line.
            p.setPen(QPen(T.alpha(T.HIGHLIGHT, 0.85), max(1.0, R * 0.055), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(v0, v1)
            # Inner "table" facet edge, like a cut stone.
            p.setPen(QPen(T.alpha(T.SOFT, 0.22), max(0.7, R * 0.025)))
            p.drawLine(QPointF(v0.x() * 0.62 + cx * 0.38, v0.y() * 0.62 + cy * 0.38),
                       QPointF(v1.x() * 0.62 + cx * 0.38, v1.y() * 0.62 + cy * 0.38))
            if i in (0, 5):
                p.setPen(QPen(T.alpha(QColor(255, 255, 255), 0.2), max(0.8, R * 0.03)))
                p.drawLine(QPointF(v0.x() * 0.75 + cx * 0.25, v0.y() * 0.75 + cy * 0.25),
                           QPointF(outer.x() * 0.6 + cx * 0.4, outer.y() * 0.6 + cy * 0.4))
            p.restore()

    def _almond(self, cx, cy, er, openness):
        path = QPainterPath()
        path.moveTo(cx - er, cy)
        path.quadTo(cx, cy - er * 1.05 * openness, cx + er, cy)
        path.quadTo(cx, cy + er * 1.05 * openness, cx - er, cy)
        path.closeSubpath()
        return path

    def _draw_eye(self, p, cx, cy, R):
        openness = max(0.05, self.eye * (1 - self.blink))
        er = R * (0.56 + 0.08 * self.open)
        almond = self._almond(cx, cy, er, openness)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 13, 34))
        p.drawPath(almond)
        p.save()
        p.setClipPath(almond)
        ix = cx + self.look[0] * er * 0.32
        iy = cy + self.look[1] * er * 0.22
        ir = er * 0.66
        grad = QRadialGradient(QPointF(ix, iy), ir)
        grad.setColorAt(0.0, QColor(212, 170, 250))
        grad.setColorAt(0.35, QColor(150, 100, 210))
        grad.setColorAt(0.75, QColor(84, 50, 140))
        grad.setColorAt(1.0, QColor(40, 26, 70))
        p.setBrush(grad)
        p.drawEllipse(QPointF(ix, iy), ir, ir)
        p.setPen(QPen(T.alpha(T.HIGHLIGHT, 0.18), max(0.6, R * 0.02)))
        for k in range(12):
            a = math.radians(k * 30 + self.t * 6)
            p.drawLine(QPointF(ix + math.cos(a) * ir * 0.42, iy + math.sin(a) * ir * 0.42),
                       QPointF(ix + math.cos(a) * ir * 0.9, iy + math.sin(a) * ir * 0.9))
        pr = er * 0.24 * (1 + 0.45 * min(1.0, self.pupil))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(8, 5, 14))
        p.drawEllipse(QPointF(ix, iy), pr, pr)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(QPointF(ix + pr * 0.55, iy - pr * 0.6), pr * 0.38, pr * 0.38)
        p.setBrush(QColor(255, 255, 255, 120))
        p.drawEllipse(QPointF(ix - pr * 0.45, iy + pr * 0.5), pr * 0.17, pr * 0.17)
        p.restore()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(T.alpha(T.SOFT, 0.75), max(1.0, R * 0.04)))
        p.drawPath(almond)

    def _draw_closed_eye(self, p, cx, cy, R):
        er = R * 0.46
        path = QPainterPath()
        path.moveTo(cx - er, cy - er * 0.05)
        path.quadTo(cx, cy + er * 0.45, cx + er, cy - er * 0.05)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(T.alpha(T.SOFT, 0.85), max(1.2, R * 0.06), Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        if self.mood == "sleeping":
            for k in range(3):
                ph = (self.t * 0.35 + k / 3.0) % 1.0
                a = math.sin(math.pi * ph)
                p.setPen(Qt.NoPen)
                p.setBrush(T.alpha(T.HIGHLIGHT, 0.7 * a))
                p.drawPath(_star(cx + R * (0.55 + 0.35 * ph), cy - R * (0.5 + 0.6 * ph), R * (0.07 + 0.05 * k)))

    def _draw_orbit(self, p, cx, cy, R):
        p.setPen(Qt.NoPen)
        for k in range(3):
            base = self.t * 3.2 + k * 2 * math.pi / 3
            for trail in range(6):
                a = base - trail * 0.16
                x, y = cx + math.cos(a) * R * 1.28, cy + math.sin(a) * R * 1.28 * 0.92
                alpha = (1 - trail / 6) * 0.9
                p.setBrush(T.alpha(T.HIGHLIGHT if trail == 0 else T.SOFT, alpha))
                s = R * (0.075 - trail * 0.009)
                p.drawEllipse(QPointF(x, y), s, s)

    def _draw_sparkles(self, p, cx, cy, R):
        p.setPen(Qt.NoPen)
        for s in self.sparkles:
            a = math.sin(math.pi * s["life"] / s["max"])
            p.setBrush(T.alpha(s["color"], 0.9 * a))
            p.drawPath(_star(cx + s["x"] * R, cy + s["y"] * R, s["size"] * R * (0.6 + 0.4 * a)))


def render_image(size, mood="idle", icon=True):
    """A static crystal image. icon=True fills the square with no glow (exe, tray and window icons)."""
    c = Crystal()
    c.assemble = 1.0
    c.mood = mood
    c.look = [0.15, 0.1]
    o, e, g, _ = TARGETS[mood]
    c.open, c.eye, c.glow = (0.0, e, 0.0) if icon else (o, e, g * 0.6)
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    c.draw(p, size / 2, size / 2 + (size * 0.01 if icon else 0), size * (0.47 if icon else 0.36))
    p.end()
    return img
