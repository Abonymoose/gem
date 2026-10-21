"""Gem's on-screen presence: the Dynamic Island, the command bar and menus.

Qt owns the main thread. Other threads talk to it only through the Bridge
signals, which Qt delivers on the GUI thread.
"""
import logging
import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLineEdit, QMenu, QWidget

from ..runtime import svc
from ..state import ALWAYS_LISTENING, PUSH_TO_TALK
from . import theme as T
from .island import Island

log = logging.getLogger("gem.overlay")

MENU_STYLE = """
QMenu { background: #0b0b0d; color: #f0eafc; border: 1px solid #26262c; border-radius: 12px; padding: 6px; }
QMenu::item { padding: 7px 22px 7px 14px; border-radius: 7px; }
QMenu::item:selected { background: #1f1a2e; }
QMenu::separator { height: 1px; background: #222228; margin: 5px 8px; }
QMenu::indicator { width: 0px; }
QMenu::item:checked { color: #c4a0f0; font-weight: 600; }
"""


class Bridge(QObject):
    show = Signal(object)
    dismiss = Signal()
    suppress = Signal(float)
    pulse = Signal()
    command_bar = Signal()
    dashboard = Signal(str)
    quit = Signal()
    fx = Signal(str, float)


class CommandBar(QWidget):
    WIDTH = 520
    LOGO_X = 36                 # logo centre from the bar's left edge (clear of the rounded end)
    LOGO_R = 10
    TEXT_GAP = 16               # space between the logo and the text

    def __init__(self, ctrl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.ctrl = ctrl
        self.history = []
        self.index = 0
        self.resize(self.WIDTH + 40, 92)
        self.edit = QLineEdit(self)
        left = 20 + self.LOGO_X + self.LOGO_R + self.TEXT_GAP
        self.edit.setGeometry(left, 26, 20 + self.WIDTH - 24 - left, 36)
        self.edit.setPlaceholderText("Ask Gem anything…")
        self.edit.setFont(T.font(16))
        self.edit.setStyleSheet("QLineEdit { background: transparent; border: none; color: #f4f0fb; "
                                "selection-background-color: #6b3fa0; }")
        self.edit.returnPressed.connect(self._submit)
        self.edit.installEventFilter(self)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(20, 16, self.WIDTH, 56)
        for i in range(8):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(22 * (1 - i / 8))))
            p.drawRoundedRect(box.adjusted(-i * 1.5, -i + 3, i * 1.5, i * 2 + 3), 28 + i, 28 + i)
        p.setBrush(T.ISLAND)
        p.setPen(QPen(T.alpha(T.SOFT, 0.35), 1.2))
        p.drawRoundedRect(box, 28, 28)
        self.ctrl.island.crystal.draw(p, box.left() + self.LOGO_X, box.center().y(), self.LOGO_R)
        p.end()

    def eventFilter(self, obj, e):
        if e.type() == e.Type.KeyPress:
            if e.key() == Qt.Key_Escape:
                self.hide()
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
            self.hide()

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

    def _submit(self):
        text = self.edit.text().strip()
        self.hide()
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
        self.bridge.show.connect(lambda d: self.island.show_card(d.get("you"), d.get("text"), d.get("card"),
                                                                  d.get("seconds")))
        self.bridge.dismiss.connect(lambda: self.island.dismiss())
        self.bridge.suppress.connect(self._on_suppress)
        self.bridge.pulse.connect(lambda: self.island.pulse())
        self.bridge.command_bar.connect(self.open_command_bar_now)
        self.bridge.dashboard.connect(self._open_dashboard)
        self.bridge.quit.connect(self.app.quit)
        self.bridge.fx.connect(lambda kind, secs: self.island.play_fx(kind, secs))

        self.screen_geo = QGuiApplication.primaryScreen().geometry()
        QGuiApplication.primaryScreen().geometryChanged.connect(self._screen_changed)
        self.island = Island(self)
        self.bar = CommandBar(self)
        self.dashboard = None
        self.menu_open = False

        self._last = time.monotonic()
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _screen_changed(self, geo):
        self.screen_geo = geo

    # ── Thread-safe API ──────────────────────────────────────────────────────

    def caption(self, gem=None, you=None, seconds=None, card=None):
        if gem is None and you is None and card is None:
            return
        self.bridge.show.emit({"text": gem, "you": you, "seconds": seconds, "card": card})

    def dismiss(self):
        self.bridge.dismiss.emit()

    def suppress(self, seconds):
        """Hide right away (e.g. so screenshots don't include Gem)."""
        self.bridge.suppress.emit(float(seconds))

    def flash(self, seconds=2.5):
        self.bridge.pulse.emit()

    def fx(self, kind, seconds=1.2):
        """A one-off island effect ("roll", "confetti")."""
        self.bridge.fx.emit(kind, float(seconds))

    def open_command_bar(self):
        self.bridge.command_bar.emit()

    def open_dashboard(self, page="home"):
        self.bridge.dashboard.emit(page)

    def quit(self):
        self.bridge.quit.emit()

    def run(self):
        self.app.exec()

    # ── GUI-thread slots ─────────────────────────────────────────────────────

    def _on_suppress(self, seconds):
        self.island.suppress_until = time.monotonic() + seconds
        self.island.opacity = 0.0
        self.island.hide()

    def open_command_bar_now(self):
        self.bar.open_bar(self.screen_geo.center().x(), self.screen_geo.top() + 40)

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
        m.addAction("Routines", lambda: self._open_dashboard("routines"))
        m.addAction("Settings", lambda: self._open_dashboard("settings"))
        m.addSeparator()
        m.addAction("Quit Gem", lambda: svc.assistant.quit())
        self.menu_open = True
        try:
            m.exec(pos)
        finally:
            self.menu_open = False

    # ── Frame loop ───────────────────────────────────────────────────────────

    def _tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        try:
            visible, animating = self.island.step(dt)
            if self.bar.isVisible():
                self.bar.update()
            want = 16 if animating or self.bar.isVisible() else 33 if visible else 120
            if self.timer.interval() != want:
                self.timer.setInterval(want)
        except Exception:
            log.exception("Overlay frame failed")
