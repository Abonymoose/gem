"""The Dynamic Island: a small black pill hugging the top edge of the screen.

It's Gem's whole on-screen presence. Idle it's a tiny pill with the crystal;
it shows live activities (timers, focus, music, calls, quiet time), widens
with a waveform while you talk, and opens into a card for answers. Sizes
animate on springs. Clicks pass straight through it to whatever is
underneath, unless you rest the mouse on it for a moment.
"""
import ctypes
import math
import os
import time
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QConicalGradient, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..runtime import svc
from ..state import ALWAYS_LISTENING, PUSH_TO_TALK
from . import theme as T
from .cardview import CardContent, draw_ring
from .crystal import Crystal

PAD_X = 30            # room around the island for the glow
PAD_Y = 30
EAR = 9               # concave corners joining the island to the screen edge
CARD_W = 468

F_ROW = T.font(13, QFont.DemiBold)
F_ROW_LIGHT = T.font(13)
F_DIM = T.font(11)
F_VALUE = T.font(13, QFont.DemiBold)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x20, 0x80000, 0x80, 0x08000000
_u32 = ctypes.windll.user32
_u32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_u32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]


class Spring:
    """A slightly bouncy spring, for the Apple-like resizing."""

    def __init__(self, x, stiffness=300.0, damping=0.78):
        self.x, self.v = float(x), 0.0
        self.k = stiffness
        self.c = 2 * math.sqrt(stiffness) * damping

    def step(self, target, dt):
        for _ in range(2):                 # two half-steps keep it stable at 30 fps
            h = dt / 2
            self.v += (self.k * (target - self.x) - self.c * self.v) * h
            self.x += self.v * h
        return self.x


def _countdown(sec):
    sec = max(0, int(math.ceil(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


class Island(QWidget):
    def __init__(self, ctrl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.ctrl = ctrl
        self.crystal = Crystal()
        self.content = CardContent()
        self.content_version = 0
        self.w, self.h, self.r = Spring(150), Spring(0), Spring(14)
        self.opacity = 0.0
        self.glow = 0.0
        self.mode = "launch"
        self.shown = ("launch", 0)
        self.content_alpha = 1.0
        self.levels = deque([0.0] * 26, maxlen=26)
        self.t = 0.0
        self.started = time.monotonic()
        self.card_until = 0.0
        self._you_at = 0.0
        self.toast_text = ""
        self.toast_until = 0.0
        self.suppress_until = 0.0
        self.interactive = False
        self._hover_since = None
        self._left_since = None
        self.activity = None
        self._activity_at = 0.0
        self._music = None
        self._music_at = 0.0
        self.fullscreen = False
        self._fs_at = 0.0
        self._clickthrough = None
        self.resize(220, 80)

    # ── Window plumbing ──────────────────────────────────────────────────────

    def _hwnd(self):
        return ctypes.c_void_p(int(self.winId()))

    def set_clickthrough(self, on):
        if on == self._clickthrough:
            return
        hwnd = self._hwnd()
        style = _u32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        style = style | WS_EX_TRANSPARENT if on else style & ~WS_EX_TRANSPARENT
        _u32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        self._clickthrough = on

    def screen_geo(self):
        return self.ctrl.screen_geo

    def island_rect_global(self):
        g = self.screen_geo()
        return QRectF(g.center().x() - self.w.x / 2, g.top(), self.w.x, max(0.0, self.h.x))

    def _place(self):
        g = self.screen_geo()
        need_w = int(max(self.w.x, 60) + PAD_X * 2)
        need_h = int(max(self.h.x, 0) + PAD_Y)
        if abs(need_w - self.width()) > 1 or abs(need_h - self.height()) > 1:
            self.setGeometry(int(g.center().x() - need_w / 2), g.top(), need_w, max(need_h, 8))

    # ── Content from the controller ──────────────────────────────────────────

    def show_card(self, you=None, text=None, card=None, seconds=None):
        now = time.monotonic()
        if you is not None:
            self._you_at = now
        # Your words belong to the current exchange only; alerts never carry them.
        asked = bool(self.content.you) and now - getattr(self, "_you_at", 0) < 20
        if you is None and (not asked or (card or {}).get("kind") == "alert"):
            self.content.you = ""
            asked = False
        if text and not card and you is None and not asked and len(text) <= 52:
            self.toast_text = text.rstrip(".")
            self.toast_until = now + max(2.2, min(4.5, seconds or 3.0))
            return
        self.content.set_content(you=you, text=text, card=card)
        self.content_version += 1
        kind = self.content.kind
        if seconds is None:
            seconds = 8.0 if kind == "pending" else max(3.5, len(self.content.text) / 12.0)
        if kind in ("timer", "focus", "weather", "system", "todo", "timers", "schedule", "briefing", "music", "web",
                    "routine", "draft"):
            seconds = max(seconds, 6.5)
        if kind == "alert":
            seconds = max(seconds, 9.0)
        seconds *= float((svc.config.get("appearance") or {}).get("card_seconds", 1.0) or 1.0)
        self.card_until = time.monotonic() + seconds
        self.toast_until = 0.0

    def dismiss(self):
        self.card_until = 0.0
        self.toast_until = 0.0

    def pulse(self):
        self.w.v += 140.0
        self.h.v += 30.0

    # ── State → what to show ─────────────────────────────────────────────────

    def _card_active(self, now):
        st = svc.state
        if self.card_until <= 0:
            return False
        if st.speaking:
            self.card_until = max(self.card_until, now + 1.6)
        if self.content.kind == "pending" and st.thinking:
            self.card_until = max(self.card_until, now + 1.0)
        if now > self.card_until:
            self.card_until = 0.0
            return False
        return True

    def _choose_mode(self, now):
        st = svc.state
        app = svc.config.get("appearance") or {}
        if now < self.suppress_until or st.hidden:
            return "hidden"
        if now - self.started < 2.3:
            return "launch"
        if st.key_held:
            return "listening" if st.effective_mode == PUSH_TO_TALK else "muted"
        if self._card_active(now):
            return "pending" if self.content.kind == "pending" else "card"
        if st.thinking:
            return "pending"
        if now < self.toast_until:
            return "toast"
        if self.interactive:
            return "hover"
        if self.fullscreen and app.get("hide_in_fullscreen", True):
            return "hidden"
        if self.activity:
            return "activity"
        if app.get("island_when_idle", True):
            return "idle"
        return "hidden"

    def _mood(self, mode):
        st = svc.state
        if mode == "launch":
            return "launch"
        if mode == "listening":
            return "listening"
        if mode == "muted":
            return "muted"
        if mode == "pending":
            return "thinking"
        if mode == "card":
            if self.content.kind == "alert":
                return "alert"
            return "speaking" if st.speaking else "idle"
        if st.gaming:
            return "gaming"
        if st.snoozed:
            return "sleeping"
        return "idle"

    def _target(self, mode):
        """(width, height, corner radius) for a mode."""
        if mode == "hidden":
            return 70, 0, 0
        if mode == "launch":
            return 170, 40, 20
        if mode == "idle":
            return 118, 30, 15
        if mode == "listening":
            return 372, 46, 23
        if mode == "muted":
            return 236, 36, 18
        if mode == "hover":
            return 340, 48, 24
        if mode == "toast":
            return min(470, 78 + QFontMetrics(F_ROW).horizontalAdvance(self.toast_text)), 36, 18
        if mode == "activity":
            a = self.activity
            tw = QFontMetrics(F_ROW).horizontalAdvance(a["label"]) + QFontMetrics(F_VALUE).horizontalAdvance(a["value"])
            return min(440, 104 + tw), 36, 18
        if mode == "pending":
            text = self.content.you or "Thinking"
            return min(470, 124 + QFontMetrics(F_ROW_LIGHT).horizontalAdvance(text)), 46, 23
        if mode == "card":
            return CARD_W, self.content.height(CARD_W - 64) + 40, 28
        return 118, 30, 15

    # ── Live activities ──────────────────────────────────────────────────────

    def _refresh_activity(self, now):
        if now - self._activity_at < 0.5:
            return
        self._activity_at = now
        st = svc.state
        act = None
        if st.in_call:
            act = {"kind": "call", "label": "On a call", "value": "quiet"}
        if act is None:
            try:
                from ..skills import timers
                running = timers._items("timer")
            except Exception:
                running = []
            if running:
                it = running[0]
                total = max(1.0, it["at"] - it["created"])
                act = {"kind": "timer", "label": (it["label"] or "Timer").capitalize(),
                       "value": _countdown(it["at"] - time.time()), "progress": (it["at"] - time.time()) / total}
        if act is None and st.focusing:
            total = float(svc.config["focus"].get("work_minutes", 25)) * 60
            left = st.focus_until - time.time()
            act = {"kind": "focus", "label": "Focus", "value": _countdown(left), "progress": left / max(total, left)}
        if act is None and st.away_until:
            back = "" if st.away_until == math.inf else                 "back " + time.strftime("%I:%M", time.localtime(st.away_until)).lstrip("0")
            act = {"kind": "away", "label": "Away", "value": back}
        if act is None and st.dictating:
            act = {"kind": "dictating", "label": "Dictating", "value": ""}
        if act is None:
            if now - self._music_at > 3.0:
                self._music_at = now
                self._music = self._spotify_song()
            if self._music:
                act = {"kind": "music", "label": self._music, "value": ""}
        if act is None and st.snoozed:
            until = "" if st.quiet_indefinitely else time.strftime("%I:%M", time.localtime(st.snoozed_until)).lstrip("0")
            act = {"kind": "quiet", "label": "Quiet", "value": ("until " + until) if until else "say I'm back"}
        if act is None and st.gaming:
            act = {"kind": "gaming", "label": "Gaming", "value": ""}
        if act and act["kind"] == "music":
            fm = QFontMetrics(F_ROW)
            act["label"] = fm.elidedText(act["label"], Qt.ElideRight, 220)
        self.activity = act

    @staticmethod
    def _spotify_song():
        try:
            from ..winapi import top_windows
            for _, title, proc in top_windows():
                if proc == "spotify.exe" and " - " in title:
                    artist, song = title.split(" - ", 1)
                    return song
        except Exception:
            pass
        return None

    # ── Hover → interactive ──────────────────────────────────────────────────

    def _update_hover(self, now, mode):
        pos = QCursor.pos()
        rect = self.island_rect_global().adjusted(-6, 0, 6, 6)
        inside = rect.contains(QPointF(pos))
        if self.interactive:
            if inside or self.ctrl.menu_open:
                self._left_since = None
            else:
                self._left_since = self._left_since or now
                if now - self._left_since > 0.3:
                    self.interactive = False
                    self._left_since = None
        elif inside and mode in ("idle", "activity", "toast"):
            self._hover_since = self._hover_since or now
            if now - self._hover_since > 0.45:
                self.interactive = True
                self._hover_since = None
        else:
            self._hover_since = None
        self.set_clickthrough(not self.interactive)

    def mousePressEvent(self, e):
        if not self.interactive:
            return
        if e.button() == Qt.LeftButton:
            self.ctrl.open_command_bar_now()
        elif e.button() == Qt.RightButton:
            self.ctrl.context_menu(e.globalPosition().toPoint())

    # ── Frame ────────────────────────────────────────────────────────────────

    def step(self, dt):
        now = time.monotonic()
        self.t += dt
        st = svc.state
        if now - self._fs_at > 1.0:
            self._fs_at = now
            try:
                from ..winapi import foreground_is_fullscreen
                self.fullscreen = foreground_is_fullscreen(os.getpid())
            except Exception:
                self.fullscreen = False
        self._refresh_activity(now)
        mode = self._choose_mode(now)
        self._update_hover(now, mode)
        self.mode = mode

        key = (mode, self.content_version if mode in ("card", "pending") else 0)
        if key != self.shown:
            self.content_alpha -= dt * 14
            if self.content_alpha <= 0.0:
                self.content_alpha = 0.0
                self.shown = key
        else:
            self.content_alpha = min(1.0, self.content_alpha + dt * 7)

        tw, th, tr = self._target(mode)
        self.w.step(tw, dt)
        self.h.step(th, dt)
        self.r.step(tr, dt)
        self.h.x = max(0.0, self.h.x)
        want_opacity = 0.0 if mode == "hidden" else 1.0
        self.opacity += (want_opacity - self.opacity) * (1 - math.exp(-(14 if want_opacity else 8) * dt))

        level = svc.listener.level if (svc.listener and st.key_held) else 0.0
        self.levels.append(min(1.0, level * 3.2))
        target_glow = 1.0 if mode == "listening" else (0.6 + 0.4 * math.sin(self.t * 6)) if (
            mode == "card" and self.content.kind == "alert") else 0.0
        self.glow += (target_glow - self.glow) * (1 - math.exp(-10 * dt))
        self.crystal.step(dt, self._mood(mode), level)

        visible = self.opacity > 0.01 or mode != "hidden"
        if visible:
            self._place()
            if not self.isVisible():
                self.show()
                self.set_clickthrough(True)
                self._clickthrough = True
            self.update()
        elif self.isVisible():
            self.hide()
        animating = abs(self.w.v) + abs(self.h.v) > 1 or mode not in ("idle", "hidden", "activity")
        return visible, animating

    # ── Painting ─────────────────────────────────────────────────────────────

    def _shape(self, rect, r):
        x0, x1, h = rect.left(), rect.right(), rect.height()
        r = max(0.0, min(r, h / 2, rect.width() / 2))
        e = min(EAR, h * 0.45)
        path = QPainterPath()
        path.moveTo(x0 - e, 0)
        path.quadTo(x0, 0, x0, e)
        path.lineTo(x0, h - r)
        path.arcTo(QRectF(x0, h - 2 * r, 2 * r, 2 * r), 180, 90)
        path.lineTo(x1 - r, h)
        path.arcTo(QRectF(x1 - 2 * r, h - 2 * r, 2 * r, 2 * r), 270, 90)
        path.lineTo(x1, e)
        path.quadTo(x1, 0, x1 + e, 0)
        path.closeSubpath()
        return path

    def paintEvent(self, _):
        if self.opacity <= 0.01 or self.h.x < 1:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setOpacity(self.opacity)
        w, h = self.w.x, self.h.x
        rect = QRectF((self.width() - w) / 2, 0, w, h)
        path = self._shape(rect, self.r.x)

        if self.glow > 0.02:
            boost = 0.7 + 0.5 * min(1.0, max(self.levels) if self.levels else 0)
            grad = QConicalGradient(rect.center(), (self.t * 90) % 360)
            stops = T.GLOW + [T.GLOW[0]]
            for i in range(7):
                k = i / 6
                for j, c in enumerate(stops):
                    grad.setColorAt(j / (len(stops) - 1), T.alpha(c, self.glow * boost * 0.55 * (1 - k) ** 2))
                p.setPen(QPen(grad, 2 + i * 3.2))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)

        p.fillPath(path, T.ISLAND)
        p.setPen(QPen(T.ISLAND_EDGE, 1))
        p.drawPath(path)
        if self.glow > 0.02:
            grad = QConicalGradient(rect.center(), (self.t * 90) % 360)
            stops = T.GLOW + [T.GLOW[0]]
            for j, c in enumerate(stops):
                grad.setColorAt(j / (len(stops) - 1), T.alpha(c, self.glow * 0.9))
            p.setPen(QPen(grad, 1.6))
            p.drawPath(path)

        p.setClipPath(path)
        p.setOpacity(self.opacity * self.content_alpha)
        getattr(self, "_paint_" + self.shown[0], lambda *_: None)(p, rect)
        p.end()

    # Row helpers -------------------------------------------------------------

    def _crystal(self, p, x, cy, r):
        self.crystal.draw(p, x, cy, r)

    def _text(self, p, x, cy, w, text, font=F_ROW, color=T.TEXT, align=Qt.AlignLeft):
        p.setFont(font)
        p.setPen(color)
        fm = QFontMetrics(font)
        p.drawText(QRectF(x, cy - fm.height() / 2, w, fm.height()), align | Qt.AlignVCenter,
                   fm.elidedText(text, Qt.ElideRight, int(max(0, w))))

    def _paint_launch(self, p, rect):
        self._crystal(p, rect.center().x(), rect.height() / 2 + 1, 12)

    def _paint_idle(self, p, rect):
        cy = rect.height() / 2 + 1
        self._crystal(p, rect.center().x(), cy, 7.5)
        st = svc.state
        if st.mode == ALWAYS_LISTENING and st.ears_open():
            # Like the iPhone's orange dot: the mic is live.
            a = 0.65 + 0.35 * math.sin(self.t * 3)
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(QColor(167, 139, 250), a))
            p.drawEllipse(QPointF(rect.right() - 16, cy), 3.2, 3.2)

    def _paint_toast(self, p, rect):
        cy = rect.height() / 2 + 1
        self._crystal(p, rect.left() + 24, cy, 7.5)
        self._text(p, rect.left() + 42, cy, rect.width() - 60, self.toast_text)

    def _paint_hover(self, p, rect):
        st = svc.state
        self._crystal(p, rect.left() + 26, 24, 10)
        mode = "Push to talk" if st.mode == PUSH_TO_TALK else "Always listening"
        status = st.describe().replace("Push to talk", "").replace("Always listening", "").strip(" ·")
        self._text(p, rect.left() + 48, 17, rect.width() - 70, "Gem · " + mode + (" · " + status if status else ""))
        self._text(p, rect.left() + 48, 33, rect.width() - 70, "Click to type  ·  Right-click for menu",
                   F_DIM, T.TEXT_DIM)

    def _paint_activity(self, p, rect):
        a = self.activity
        if not a:
            return
        cy = rect.height() / 2 + 1
        self._crystal(p, rect.left() + 22, cy, 7.5)
        ix = rect.left() + 46
        kind = a["kind"]
        if kind in ("timer", "focus"):
            draw_ring(p, ix, cy, 7, max(0.0, min(1.0, a.get("progress", 0))), 2.6)
        elif kind == "call":
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(QColor(52, 211, 153), 0.7 + 0.3 * math.sin(self.t * 4)))
            p.drawEllipse(QPointF(ix, cy), 4.5, 4.5)
        elif kind == "dictating":
            p.setPen(Qt.NoPen)
            p.setBrush(T.alpha(QColor(248, 113, 113), 0.7 + 0.3 * math.sin(self.t * 4)))
            p.drawEllipse(QPointF(ix, cy), 4.5, 4.5)
        elif kind == "music":
            p.setPen(Qt.NoPen)
            for k in range(3):
                hgt = 4 + 8 * abs(math.sin(self.t * (4 + k * 1.4) + k))
                p.setBrush(T.alpha(T.SOFT, 0.9))
                p.drawRoundedRect(QRectF(ix - 6 + k * 4.5, cy + 6 - hgt, 3, hgt), 1.5, 1.5)
        elif kind == "quiet":
            moon = QPainterPath()
            moon.addEllipse(QPointF(ix, cy), 6, 6)
            cut = QPainterPath()
            cut.addEllipse(QPointF(ix + 3.2, cy - 2.4), 5.2, 5.2)
            p.setPen(Qt.NoPen)
            p.setBrush(T.SOFT)
            p.drawPath(moon.subtracted(cut))
        elif kind == "away":
            p.setPen(QPen(T.SOFT, 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(ix, cy), 6, 6)
            p.drawLine(QPointF(ix, cy), QPointF(ix, cy - 3.6))
            p.drawLine(QPointF(ix, cy), QPointF(ix + 2.8, cy + 1.2))
        elif kind == "gaming":
            p.setPen(QPen(T.SOFT, 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(ix, cy), 5.5, 5.5)
            p.drawLine(QPointF(ix - 8, cy), QPointF(ix + 8, cy))
            p.drawLine(QPointF(ix, cy - 8), QPointF(ix, cy + 8))
        vw = QFontMetrics(F_VALUE).horizontalAdvance(a["value"])
        self._text(p, ix + 14, cy, rect.right() - ix - 30 - vw, a["label"])
        if a["value"]:
            self._text(p, rect.right() - 18 - vw, cy, vw + 2, a["value"], F_VALUE,
                       T.TEXT_DIM if kind in ("call", "quiet", "away") else T.SOFT, Qt.AlignRight)

    def _paint_listening(self, p, rect):
        cy = rect.height() / 2 + 1
        self._crystal(p, rect.left() + 28, cy, 11)
        self._text(p, rect.left() + 52, cy, 120, "Listening", F_ROW, T.TEXT)
        n = len(self.levels)
        bw, gap = 3.2, 2.6
        total = n * bw + (n - 1) * gap
        x = rect.right() - 22 - total
        p.setPen(Qt.NoPen)
        for i, lv in enumerate(self.levels):
            idle = 0.08 + 0.05 * math.sin(self.t * 5 + i * 0.6)
            hgt = 3 + 22 * max(idle, lv)
            c = T.mix(T.GLOW[0], T.GLOW[1], i / n) if i < n * 0.6 else T.mix(T.GLOW[1], T.GLOW[2], (i - n * 0.6) / (n * 0.4))
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x + i * (bw + gap), cy - hgt / 2, bw, hgt), bw / 2, bw / 2)

    def _paint_muted(self, p, rect):
        cy = rect.height() / 2 + 1
        self._crystal(p, rect.left() + 22, cy, 7.5)
        self._text(p, rect.left() + 42, cy, rect.width() - 60, "Muted while you hold Caps Lock", F_ROW, T.TEXT_DIM)

    def _paint_pending(self, p, rect):
        cy = rect.height() / 2 + 1
        self._crystal(p, rect.left() + 28, cy, 11)
        text = self.content.you or "Thinking"
        self._text(p, rect.left() + 52, cy, rect.width() - 112, text, F_ROW_LIGHT, T.TEXT)
        p.setPen(Qt.NoPen)
        for k in range(3):
            a = 0.3 + 0.7 * max(0.0, math.sin(self.t * 5 - k * 0.7))
            p.setBrush(T.alpha(T.SOFT, a))
            p.drawEllipse(QPointF(rect.right() - 46 + k * 11, cy), 3, 3)

    def _paint_card(self, p, rect):
        # Laid out at the final width; the island's shape reveals it as it grows.
        left = rect.center().x() - CARD_W / 2
        self._crystal(p, left + CARD_W - 26, 24, 7)
        self.content.paint(p, left + 24, 18, CARD_W - 64, self.t)
