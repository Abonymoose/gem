"""Gem's on-screen presence: the crystal and answer card at the top centre of
the screen, the edge glow, and the command bar.

Qt owns the main thread. Other threads talk to it only through the Bridge
signals, which Qt delivers on the GUI thread.
"""
import ctypes
import logging
import math
import time

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

from ..runtime import svc
from ..state import ALWAYS_LISTENING, PUSH_TO_TALK
from . import theme as T
from .cardview import MARGIN as CARD_MARGIN, CardView
from .crystal import Crystal
from .edge import EdgeGlow

log = logging.getLogger("gem.overlay")

CRYSTAL_BOX = 136
CRYSTAL_R = 25
TOP_OFFSET = -18          # the window starts a little above the screen; the crystal sits ~20px down

MENU_STYLE = """
QMenu { background: #171127; color: #ece3fb; border: 1px solid #2f2350; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 22px 7px 14px; border-radius: 6px; }
QMenu::item:selected { background: #2a1d45; }
QMenu::separator { height: 1px; background: #2a1f42; margin: 5px 8px; }
QMenu::indicator { width: 0px; }
QMenu::item:checked { color: #c4a0f0; font-weight: 600; }
"""


class Bridge(QObject):
    show = Signal(object)
    dismiss = Signal()
    suppress = Signal(float)
    command_bar = Signal()
    dashboard = Signal(str)
    quit = Signal()


class CrystalWindow(QWidget):
    def __init__(self, ctrl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool |
                         Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.ctrl = ctrl
        self.resize(CRYSTAL_BOX, CRYSTAL_BOX)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _):
        c = self.ctrl
        if c.opacity <= 0.01:
            return
        p = QPainter(self)
        c.crystal.draw(p, self.width() / 2, self.height() / 2, CRYSTAL_R * c.scale, opacity=c.opacity)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.ctrl.open_command_bar_now()
        elif e.button() == Qt.RightButton:
            self.ctrl.context_menu(e.globalPosition().toPoint())


class CommandBar(QWidget):
    WIDTH = 520

    def __init__(self, ctrl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.ctrl = ctrl
        self.history = []
        self.index = 0
        self.resize(self.WIDTH + 40, 92)
        self.edit = QLineEdit(self)
        self.edit.setGeometry(44, 26, self.WIDTH - 40, 36)
        self.edit.setPlaceholderText("Ask Gem anything…")
        self.edit.setFont(T.font(16))
        self.edit.setStyleSheet("QLineEdit { background: transparent; border: none; color: #f0eafc; "
                                "selection-background-color: #6b3fa0; }")
        self.edit.returnPressed.connect(self._submit)
        self.edit.installEventFilter(self)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(20, 16, self.WIDTH, 56)
        for i in range(8):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(18 * (1 - i / 8))))
            p.drawRoundedRect(box.adjusted(-i * 1.5, -i + 3, i * 1.5, i * 2 + 3), 28 + i, 28 + i)
        g = QLinearGradient(box.topLeft(), box.bottomLeft())
        g.setColorAt(0, QColor(34, 25, 56, 250))
        g.setColorAt(1, QColor(20, 14, 36, 250))
        p.setBrush(g)
        p.setPen(QPen(T.alpha(T.SOFT, 0.35), 1.2))
        p.drawRoundedRect(box, 28, 28)
        # Small crystal glyph on the left.
        self.ctrl.crystal.draw(p, box.left() + 26, box.center().y(), 10)
        p.end()

    def eventFilter(self, obj, e):
        if e.type() == e.Type.KeyPress:
            if e.key() == Qt.Key_Escape:
                self.close_bar()
                return True
            if e.key() in (Qt.Key_Up, Qt.Key_Down) and self.history:
                self.index = max(0, min(len(self.history), self.index + (-1 if e.key() == Qt.Key_Up else 1)))
                self.edit.setText(self.history[self.index] if self.index < len(self.history) else "")
                return True
        if e.type() == e.Type.FocusOut:
            QTimer.singleShot(120, self._maybe_close)
        return super().eventFilter(obj, e)

    def _maybe_close(self):
        if not self.edit.hasFocus() and not self.isActiveWindow():
            self.close_bar()

    def open_bar(self, x, y):
        self.move(x - self.width() // 2, y)
        self.edit.clear()
        self.index = len(self.history)
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            from ..winapi import focus_window
            focus_window(int(self.winId()))
        except Exception:
            pass
        self.edit.setFocus()

    def close_bar(self):
        self.hide()

    def _submit(self):
        text = self.edit.text().strip()
        self.close_bar()
        if text:
            self.history.append(text)
            if svc.assistant:
                svc.assistant.submit_text(text)


class Overlay:
    def __init__(self, cfg):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        self.app = QApplication.instance() or QApplication([])
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setFont(T.font(13))
        self.cfg = cfg
        self.bridge = Bridge()
        self.bridge.show.connect(self._on_show)
        self.bridge.dismiss.connect(self._on_dismiss)
        self.bridge.suppress.connect(self._on_suppress)
        self.bridge.command_bar.connect(self.open_command_bar_now)
        self.bridge.dashboard.connect(self._open_dashboard)
        self.bridge.quit.connect(self.app.quit)

        self.crystal = Crystal()
        self.cwin = CrystalWindow(self)
        self.card = CardView()
        self.bar = CommandBar(self)
        self.dashboard = None
        screen = QGuiApplication.primaryScreen()
        self.screen_geo = screen.availableGeometry()
        self.edge = EdgeGlow(screen)

        self.opacity = 0.0
        self.scale = 1.0
        self.started = time.monotonic()
        self.transient_until = time.monotonic() + 6.0      # covers the launch until the "ready" card shows
        self.card_until = 0.0
        self.card_target = 0.0
        self.suppress_until = 0.0
        self._last = time.monotonic()
        self._place()

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        QGuiApplication.primaryScreen().availableGeometryChanged.connect(lambda _: self._place())

    def _appearance(self, key, default=True):
        return (self.cfg.get("appearance") or {}).get(key, default)

    def _place(self):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.screen_geo = geo
        cx = geo.center().x()
        self.cwin.move(cx - CRYSTAL_BOX // 2, geo.top() + TOP_OFFSET)
        self.card_top = geo.top() + TOP_OFFSET + CRYSTAL_BOX // 2 + CRYSTAL_R + 14 - CARD_MARGIN
        self.card.move(cx - self.card.width() // 2, self.card_top)

    # ── Thread-safe API ──────────────────────────────────────────────────────

    def caption(self, gem=None, you=None, seconds=None, card=None):
        self.bridge.show.emit({"text": gem, "you": you, "seconds": seconds, "card": card})

    def dismiss(self):
        self.bridge.dismiss.emit()

    def suppress(self, seconds):
        """Hide everything right away (e.g. so screenshots don't include Gem)."""
        self.bridge.suppress.emit(float(seconds))

    def open_command_bar(self):
        self.bridge.command_bar.emit()

    def open_dashboard(self, page="home"):
        self.bridge.dashboard.emit(page)

    def flash(self, seconds=2.5):
        self.transient_until = max(self.transient_until, time.monotonic() + seconds)

    def quit(self):
        self.bridge.quit.emit()

    def run(self):
        self.app.exec()

    # ── GUI-thread slots ─────────────────────────────────────────────────────

    def _on_show(self, d):
        text, you, card = d.get("text"), d.get("you"), d.get("card")
        if text is None and you is None and card is None:
            return
        self.card.set_content(you=you, text=text, card=card)
        kind = self.card.kind
        seconds = d.get("seconds")
        if seconds is None:
            seconds = 8.0 if kind == "pending" else max(3.5, len(self.card.text) / 12.0)
        if kind in ("timer", "focus", "weather", "system", "todo", "timers", "schedule", "briefing", "music"):
            seconds = max(seconds, 6.5)
        if kind == "alert":
            seconds = max(seconds, 9.0)
        seconds *= float(self._appearance("card_seconds", 1.0) or 1.0)
        self.card_until = time.monotonic() + seconds
        self.card_target = 1.0
        if self.card.opacity < 0.05:
            self.card.slide = 12.0
        self.card.move(self.screen_geo.center().x() - self.card.width() // 2, self.card_top)

    def _on_dismiss(self):
        self.card_until = 0.0
        self.card_target = 0.0

    def _on_suppress(self, seconds):
        self.suppress_until = time.monotonic() + seconds
        self.opacity = 0.0
        self.card.opacity = 0.0
        self.card_target = 0.0
        for w in [self.cwin, self.card] + self.edge.strips:
            w.hide()

    def open_command_bar_now(self):
        self.flash(0.5)
        self.bar.open_bar(self.screen_geo.center().x(), self.card_top + CARD_MARGIN - 8)

    def _open_dashboard(self, page):
        try:
            if self.dashboard is None:
                from .dashboard import Dashboard
                self.dashboard = Dashboard(self)
            self.dashboard.open_page(page or "home")
        except Exception:
            log.exception("Dashboard failed to open")

    def context_menu(self, pos):
        from .. import actions
        st = svc.state
        m = QMenu()
        m.setStyleSheet(MENU_STYLE)
        group = QActionGroup(m)
        for mode, name in ((PUSH_TO_TALK, "Push to talk"), (ALWAYS_LISTENING, "Always listening")):
            a = QAction(name, m, checkable=True, checked=st.mode == mode)
            a.triggered.connect(lambda _=False, md=mode: actions.run("set_mode", {"mode": md}))
            group.addAction(a)
            m.addAction(a)
        m.addSeparator()
        if st.snoozed:
            m.addAction("Resume", lambda: actions.run("resume"))
        else:
            m.addAction("Quiet for 10 minutes", lambda: actions.run("snooze", {"minutes": 10}))
            m.addAction("Quiet for 1 hour", lambda: actions.run("snooze", {"minutes": 60}))
        m.addSeparator()
        m.addAction("Type a command…", self.open_command_bar_now)
        m.addAction("Open Gem", lambda: self._open_dashboard("home"))
        m.addAction("Settings", lambda: self._open_dashboard("settings"))
        m.addSeparator()
        m.addAction("Quit Gem", lambda: svc.assistant.quit())
        m.exec(pos)

    # ── Frame loop ───────────────────────────────────────────────────────────

    def _mood(self, now):
        st = svc.state
        if now - self.started < 2.6:
            return "launch"
        if st.gaming:
            return "gaming"
        if st.ruhig:
            return "glitch"
        if st.snoozed:
            return "sleeping"
        if st.key_held:
            return "listening" if st.effective_mode == PUSH_TO_TALK else "muted"
        if st.speaking:
            return "speaking"
        if st.thinking:
            return "thinking"
        if self.card_target > 0 and self.card.kind == "alert":
            return "alert"
        return "idle"

    def _tick(self):
        try:
            self._frame()
        except Exception:
            log.exception("Overlay frame failed")

    def _frame(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        st = svc.state
        if now < self.suppress_until:
            return

        # Card lifetime: stay while Gem talks or is still working on the answer.
        if self.card_target > 0:
            if st.speaking:
                self.card_until = max(self.card_until, now + 1.6)
            if self.card.kind == "pending" and st.thinking:
                self.card_until = max(self.card_until, now + 1.0)
            if now > self.card_until:
                self.card_target = 0.0
        rate = 14 if self.card_target > self.card.opacity else 8
        self.card.opacity += (self.card_target - self.card.opacity) * (1 - math.exp(-rate * dt))
        self.card.slide *= math.exp(-14 * dt)
        card_visible = self.card.opacity > 0.01
        self.card.t += dt

        active = (now - self.started < 3.0 or st.key_held or st.speaking or st.thinking or card_visible
                  or now < self.transient_until or self.bar.isVisible())
        mini = (st.mode == ALWAYS_LISTENING and st.ears_open() and not st.in_call and not st.snoozed
                and self._appearance("mini_crystal_when_listening", True))
        visible = (active or mini) and not st.hidden
        mood = self._mood(now) if active else "mini"
        level = svc.listener.level if svc.listener and st.key_held else 0.0
        self.crystal.step(dt, mood, level)
        self.scale += ((1.0 if active else 0.62) - self.scale) * (1 - math.exp(-10 * dt))
        self.opacity += ((1.0 if visible else 0.0) - self.opacity) * (1 - math.exp(-(12 if visible else 6) * dt))

        if self.opacity > 0.01:
            if not self.cwin.isVisible():
                self.cwin.show()
            self.cwin.update()
        elif self.cwin.isVisible():
            self.cwin.hide()

        if card_visible and not st.hidden:
            if not self.card.isVisible():
                self.card.show()
            self.card.update()
        elif self.card.isVisible():
            self.card.hide()

        talking = st.key_held and st.effective_mode == PUSH_TO_TALK and not st.hidden
        self.edge.set_active(talking and self._appearance("edge_glow", True))
        self.edge.step(dt, svc.listener.level if svc.listener else 0.0)
        if self.bar.isVisible():
            self.bar.update()

        busy = self.opacity > 0.01 or card_visible or self.edge.visible or self.bar.isVisible()
        want = 16 if busy else 80
        if self.timer.interval() != want:
            self.timer.setInterval(want)
