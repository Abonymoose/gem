"""Gem's dashboard window: status, reminders, classes, to-dos, notes, memory,
conversation history and every setting, without editing JSON by hand."""
import ctypes
import datetime
import html
import json
import logging
import os
import time

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTime, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QButtonGroup, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QTimeEdit, QVBoxLayout, QWidget)

from .. import actions
from ..config import DATA_DIR, NOTES_FILE, SETTINGS_FILE, _write_json
from ..skills import control
from ..runtime import svc
from ..state import ALWAYS_LISTENING, MODE_NAMES, PUSH_TO_TALK
from . import theme as T
from ..voices import PIPER_VOICES
from .crystal import Crystal, render_image

log = logging.getLogger("gem.dashboard")

HISTORY_FILE = os.path.join(DATA_DIR, "history.jsonl")

QSS = """
QMainWindow, QWidget#Root { background: #0f0b18; }
QWidget { color: #ece3fb; font-family: "Segoe UI"; font-size: 13px; }
QFrame#Sidebar { background: #140f22; border-right: 1px solid #221a36; }
QLabel#Brand { font-size: 19px; font-weight: 600; }
QLabel#H1 { font-size: 24px; font-weight: 600; }
QLabel#H2 { font-size: 15px; font-weight: 600; }
QLabel#Muted { color: #9b88bf; }
QLabel#Faint { color: #7d6c9e; font-size: 12px; }
QLabel#Section { color: #a07cc8; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QPushButton#Nav { text-align: left; padding: 9px 14px; border-radius: 10px; color: #b5a3d6; background: transparent;
                  border: none; font-size: 14px; }
QPushButton#Nav:hover { background: #1c1530; color: #ece3fb; }
QPushButton#Nav:checked { background: #2a1d45; color: #ffffff; }
QPushButton { background: #231938; border: 1px solid #33264f; border-radius: 9px; padding: 7px 14px; }
QPushButton:hover { background: #2d2048; border-color: #43316a; }
QPushButton:pressed { background: #1c1430; }
QPushButton#Primary { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8b5cf6, stop:1 #a07cc8);
                      border: none; color: white; font-weight: 600; }
QPushButton#Primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #9a70f8, stop:1 #b08ed6); }
QPushButton#Danger { background: transparent; border: 1px solid #4a2740; color: #f0a0c0; padding: 4px 10px; }
QPushButton#Danger:hover { background: #2a1424; }
QPushButton#Seg { border-radius: 9px; padding: 8px 16px; background: #1a1330; }
QPushButton#Seg:checked { background: #3b2a5c; border-color: #6b4fa0; color: white; font-weight: 600; }
QPushButton#Chip { border-radius: 14px; padding: 5px 12px; background: #1a1330; }
QPushButton#Chip:checked { background: #3b2a5c; border-color: #6b4fa0; color: white; }
QFrame#Card { background: #150f24; border: 1px solid #241a3a; border-radius: 16px; }
QLineEdit, QComboBox, QSpinBox, QTimeEdit, QPlainTextEdit {
    background: #1a1330; border: 1px solid #2f2350; border-radius: 8px; padding: 6px 9px;
    selection-background-color: #6b3fa0; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus, QPlainTextEdit:focus { border-color: #8b5cf6; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #1a1330; border: 1px solid #2f2350; selection-background-color: #3b2a5c; }
QSpinBox::up-button, QSpinBox::down-button, QTimeEdit::up-button, QTimeEdit::down-button { width: 16px; border: none; }
QListWidget, QTableWidget, QTextBrowser { background: #140f22; border: 1px solid #221a36; border-radius: 12px;
                                          outline: none; }
QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #1d1630; }
QListWidget::item:selected { background: #241a3c; color: #ffffff; }
QListWidget::indicator, QCheckBox::indicator { width: 18px; height: 18px; }
QTableWidget { gridline-color: transparent; }
QTableWidget::item { padding: 6px; border-bottom: 1px solid #1d1630; }
QHeaderView::section { background: #140f22; color: #8f7cb5; border: none; border-bottom: 1px solid #241a3a;
                       padding: 8px 6px; font-weight: 600; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: #2f2350; border-radius: 3px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 4px; }
QScrollBar::handle:horizontal { background: #2f2350; border-radius: 3px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSlider::groove:horizontal { height: 4px; background: #2f2350; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #8b5cf6; border-radius: 2px; }
QSlider::handle:horizontal { background: white; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QToolTip { background: #1a1330; color: #ece3fb; border: 1px solid #2f2350; }
"""


def _dark_titlebar(widget):
    try:
        hwnd = int(widget.winId())
        val = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
    except Exception:
        pass


def _clock(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%I:%M %p").lstrip("0")


def _when(ts):
    d = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    if d.date() == today:
        return _clock(ts)
    if d.date() == today + datetime.timedelta(days=1):
        return "Tomorrow " + _clock(ts)
    return d.strftime("%a %d %b ") + _clock(ts)


def _left(ts):
    s = max(0, int(ts - time.time()))
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h >= 24:
        return "%dd %dh" % (h // 24, h % 24)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


# ── Small widgets ────────────────────────────────────────────────────────────

class Toggle(QAbstractButton):
    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self, duration=160, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on):
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self):
        return QSize(46, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if self._pos > 0.5:
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0, QColor(139, 92, 246))
            g.setColorAt(1, QColor(196, 160, 240))
            p.setBrush(g)
        else:
            p.setBrush(QColor(47, 35, 80))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()


class CrystalLogo(QWidget):
    def __init__(self, size=40, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.crystal = Crystal()
        self.crystal.assemble = 1.0
        self._timer = QTimer(self, interval=33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._last = time.monotonic()

    def _tick(self):
        now = time.monotonic()
        mood = "speaking" if svc.state and svc.state.speaking else "thinking" if svc.state and svc.state.thinking \
            else "listening" if svc.state and svc.state.key_held else "idle"
        self.crystal.step(now - self._last, mood)
        self._last = now
        if self.isVisible():
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        self.crystal.draw(p, self.width() / 2, self.height() / 2, self.width() * 0.3)
        p.end()


def card_frame():
    f = QFrame()
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    return f, lay


def label(text, name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def button(text, name=None, cb=None):
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    b.setCursor(Qt.PointingHandCursor)
    if cb:
        b.clicked.connect(cb)
    return b


def table(headers, stretch=1):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.NoSelection)
    t.setFocusPolicy(Qt.NoFocus)
    t.setShowGrid(False)
    h = t.horizontalHeader()
    for i in range(len(headers)):
        h.setSectionResizeMode(i, QHeaderView.Stretch if i == stretch else QHeaderView.ResizeToContents)
    if headers[-1] == "":                      # button column: content sizing ignores cell widgets
        h.setSectionResizeMode(len(headers) - 1, QHeaderView.Fixed)
        t.setColumnWidth(len(headers) - 1, 96)
    h.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    t.verticalHeader().setDefaultSectionSize(46)
    return t


def cell_button(text, cb):
    """A compact button centred in a table cell."""
    holder = QWidget()
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(6, 6, 10, 6)
    lay.addStretch()
    lay.addWidget(button(text, "Danger", cb))
    return holder


def history_entries(limit=300):
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        return [json.loads(l) for l in lines if l.strip()]
    except Exception:
        return []


# ── Pages ────────────────────────────────────────────────────────────────────

class Page(QWidget):
    title = ""

    def __init__(self):
        super().__init__()
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(34, 28, 34, 28)
        self.root.setSpacing(16)
        if self.title:
            self.root.addWidget(label(self.title, "H1"))

    def refresh(self):
        pass

    def tick(self):
        pass


class HomePage(Page):
    def __init__(self):
        super().__init__()
        self.greet = label("", "H1")
        self.status = label("", "Muted")
        self.root.addWidget(self.greet)
        self.root.addWidget(self.status)

        grid = QGridLayout()
        grid.setSpacing(16)

        f, lay = card_frame()
        lay.addWidget(label("LISTENING", "Section"))
        seg = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        for mode in (PUSH_TO_TALK, ALWAYS_LISTENING):
            b = button(MODE_NAMES[mode], "Seg")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=mode: actions.run("set_mode", {"mode": m}))
            self.mode_group.addButton(b)
            b.mode = mode
            seg.addWidget(b)
        lay.addLayout(seg)
        lay.addWidget(label("Hold Caps Lock to talk. Triple-tap it to switch modes, tap it to stop Gem talking. "
                            "Ctrl+Alt+Space to type instead.", "Faint", wrap=True))
        lay.addWidget(label("QUIET TIME", "Section"))
        q = QHBoxLayout()
        self.quiet_buttons = [button("10 min", cb=lambda: actions.run("snooze", {"minutes": 10})),
                              button("1 hour", cb=lambda: actions.run("snooze", {"minutes": 60})),
                              button("Until I say", cb=lambda: control.quiet_until_resumed())]
        self.resume_button = button("Resume", "Primary", cb=lambda: actions.run("resume"))
        for b in self.quiet_buttons + [self.resume_button]:
            q.addWidget(b)
        q.addStretch()
        lay.addLayout(q)
        lay.addStretch()
        grid.addWidget(f, 0, 0)

        f, lay = card_frame()
        lay.addWidget(label("QUICK SWITCHES", "Section"))
        self.switches = {}
        for key, name in (("voice", "Spoken replies"), ("gaming", "Gaming mode"), ("island", "Island when idle"),
                          ("cues", "Sound cues")):
            row = QHBoxLayout()
            row.addWidget(label(name))
            row.addStretch()
            t = Toggle()
            t.clicked.connect(lambda on, k=key: self._switch(k, on))
            self.switches[key] = t
            row.addWidget(t)
            lay.addLayout(row)
        lay.addStretch()
        grid.addWidget(f, 0, 1)

        f, lay = card_frame()
        lay.addWidget(label("UP NEXT", "Section"))
        self.upnext = QVBoxLayout()
        self.upnext.setSpacing(8)
        lay.addLayout(self.upnext)
        lay.addStretch()
        grid.addWidget(f, 1, 0)

        f, lay = card_frame()
        lay.addWidget(label("RECENT", "Section"))
        self.recent = QVBoxLayout()
        self.recent.setSpacing(8)
        lay.addLayout(self.recent)
        lay.addStretch()
        grid.addWidget(f, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.root.addLayout(grid)
        self.root.addStretch()

    def _switch(self, key, on):
        cfg = svc.config
        if key == "voice":
            actions.run("voice_replies", {"on": on})
        elif key == "gaming":
            actions.run("gaming_mode", {"on": on})
        elif key == "island":
            cfg.setdefault("appearance", {})["island_when_idle"] = on
            Dashboard.save_settings()
        elif key == "cues":
            cfg.setdefault("sounds", {})["cues"] = on
            Dashboard.save_settings()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()            # hide now; deleteLater only runs on the next loop pass
                item.widget().deleteLater()
            elif item.layout():
                HomePage._clear(item.layout())
                item.layout().deleteLater()

    def refresh(self):
        st = svc.state
        now = datetime.datetime.now()
        part = "evening" if now.hour < 5 else "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"
        name = svc.config.get("user_name") or ""
        self.greet.setText("Good %s%s" % (part, ", " + name if name else ""))
        for b in self.mode_group.buttons():
            b.setChecked(b.mode == st.mode)
        self.switches["voice"].setChecked(st.voice_enabled)
        self.switches["gaming"].setChecked(st.gaming)
        self.switches["island"].setChecked((svc.config.get("appearance") or {}).get("island_when_idle", True))
        self.switches["cues"].setChecked((svc.config.get("sounds") or {}).get("cues", True))
        for b in self.quiet_buttons:
            b.setVisible(not st.snoozed)
        self.resume_button.setVisible(st.snoozed)

        self._clear(self.upnext)
        from ..skills import timers
        rows = []
        nxt = timers.next_class()
        if not nxt.startswith("You have nothing"):
            rows.append(("Class", nxt.rstrip(".")))
        for it in timers._items()[:4]:
            what = (it.get("message") or it.get("label") or it["kind"]).capitalize()
            when = _left(it["at"]) + " left" if it["kind"] == "timer" else _when(it["at"])
            rows.append((it["kind"].capitalize(), "%s · %s" % (what, when)))
        if not rows:
            rows.append(("", "Nothing coming up."))
        for kind, text in rows:
            r = QHBoxLayout()
            if kind:
                k = label(kind.upper(), "Faint")
                k.setFixedWidth(70)
                r.addWidget(k)
            r.addWidget(label(text, wrap=True), 1)
            self.upnext.addLayout(r)

        self._clear(self.recent)
        entries = [e for e in history_entries(20) if e.get("you")][-4:]
        if not entries:
            self.recent.addWidget(label("Your conversations will show up here.", "Muted"))
        for e in reversed(entries):
            you = label("“%s”" % e["you"], "Faint", wrap=True)
            gem = label(e.get("gem") or "Done.", wrap=True)
            self.recent.addWidget(you)
            self.recent.addWidget(gem)

    def tick(self):
        self.status.setText(svc.state.describe() + ("  ·  Caps Lock held" if svc.state.key_held else ""))


class RemindersPage(Page):
    title = "Reminders & timers"

    def __init__(self):
        super().__init__()
        f, lay = card_frame()
        lay.addWidget(label("NEW REMINDER", "Section"))
        row = QHBoxLayout()
        self.msg = QLineEdit(placeholderText="What to remind you about")
        self.when = QLineEdit(placeholderText="When: in 20 minutes, 6 pm, tomorrow 8 am")
        self.when.setFixedWidth(270)
        add = button("Add", "Primary", self._add)
        self.msg.returnPressed.connect(self._add)
        self.when.returnPressed.connect(self._add)
        row.addWidget(self.msg, 1)
        row.addWidget(self.when)
        row.addWidget(add)
        lay.addLayout(row)
        quick = QHBoxLayout()
        quick.addWidget(label("Quick timer:", "Muted"))
        for m in (5, 10, 15, 25, 45):
            quick.addWidget(button("%d min" % m, "Chip", lambda _=False, mm=m: self._timer(mm)))
        quick.addStretch()
        lay.addLayout(quick)
        self.feedback = label("", "Muted")
        lay.addWidget(self.feedback)
        self.root.addWidget(f)
        self.table = table(["Type", "What", "When", "Left", ""], stretch=1)
        self.root.addWidget(self.table, 1)

    def _add(self):
        msg, when = self.msg.text().strip(), self.when.text().strip()
        if not msg or not when:
            self.feedback.setText("Fill in both what and when.")
            return
        self.feedback.setText(actions.run("set_reminder", {"message": msg, "time": when}) or "")
        self.msg.clear()
        self.when.clear()
        self.refresh()

    def _timer(self, minutes):
        self.feedback.setText(actions.run("set_timer", {"minutes": minutes}) or "")
        self.refresh()

    def refresh(self):
        from ..skills import timers
        items = timers._items()
        self.table.setRowCount(0)          # drop old cell widgets right away
        self.table.setRowCount(len(items))
        self._ids = []
        for r, it in enumerate(items):
            what = it.get("message") or it.get("label") or "-"
            if it.get("repeat_minutes"):
                what += "  (every %g min)" % it["repeat_minutes"]
            for c, val in enumerate((it["kind"].capitalize(), what, _when(it["at"]), _left(it["at"]))):
                self.table.setItem(r, c, QTableWidgetItem(val))
            self.table.setCellWidget(r, 4, cell_button("Cancel", lambda _=False, i=it["id"]: self._cancel(i)))
            self._ids.append(it["id"])

    def _cancel(self, item_id):
        from ..skills import timers
        timers._remove({item_id})
        self.refresh()

    def tick(self):
        from ..skills import timers
        items = timers._items()
        if [i["id"] for i in items] != getattr(self, "_ids", None):
            self.refresh()
            return
        for r, it in enumerate(items):
            cell = self.table.item(r, 3)
            if cell:
                cell.setText(_left(it["at"]))


class ClassesPage(Page):
    title = "Classes"

    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    def __init__(self):
        super().__init__()
        self.root.addWidget(label("Weekly events. Gem alerts you at the time and opens the link.", "Muted"))
        f, lay = card_frame()
        lay.addWidget(label("ADD A CLASS", "Section"))
        row = QHBoxLayout()
        self.name = QLineEdit(placeholderText="Name, e.g. Chemistry")
        self.time = QTimeEdit(QTime(16, 0))
        self.time.setDisplayFormat("h:mm AP")
        self.link = QLineEdit(placeholderText="Meeting link (optional)")
        row.addWidget(self.name, 1)
        row.addWidget(self.time)
        row.addWidget(self.link, 1)
        lay.addLayout(row)
        days = QHBoxLayout()
        self.day_buttons = []
        for d in self.DAYS:
            b = button(d[:3].capitalize(), "Chip")
            b.setCheckable(True)
            b.day = d
            self.day_buttons.append(b)
            days.addWidget(b)
        days.addStretch()
        days.addWidget(button("Add class", "Primary", self._add))
        lay.addLayout(days)
        self.feedback = label("", "Muted")
        lay.addWidget(self.feedback)
        self.root.addWidget(f)
        self.table = table(["Name", "Days", "Time", "Link", ""], stretch=3)
        self.root.addWidget(self.table, 1)

    def _add(self):
        days = [b.day for b in self.day_buttons if b.isChecked()]
        res = actions.run("schedule_add", {"name": self.name.text().strip(), "days": days,
                                           "time": self.time.time().toString("HH:mm"),
                                           "url": self.link.text().strip()})
        self.feedback.setText(res or "")
        if res and res.startswith("Added"):
            self.name.clear()
            self.link.clear()
            for b in self.day_buttons:
                b.setChecked(False)
        self.refresh()

    def _delete(self, index):
        from ..skills import timers
        with timers.store as data:
            if 0 <= index < len(data["schedule"]):
                data["schedule"].pop(index)
        self.refresh()

    def refresh(self):
        from ..skills import timers
        sched = timers._schedule()
        self.table.setRowCount(0)          # drop old cell widgets right away
        self.table.setRowCount(len(sched))
        for r, e in enumerate(sched):
            h, m = map(int, e["time"].split(":"))
            t12 = datetime.time(h, m).strftime("%I:%M %p").lstrip("0")
            vals = (e["name"].capitalize(), ", ".join(d[:3].capitalize() for d in e.get("days", [])), t12,
                    e.get("url") or "")
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(val))
            self.table.setCellWidget(r, 4, cell_button("Delete", lambda _=False, i=r: self._delete(i)))


class _DeletableList(QListWidget):
    def __init__(self, on_delete):
        super().__init__()
        self.on_delete = on_delete

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete and self.currentItem():
            self.on_delete(self.currentItem())
        else:
            super().keyPressEvent(e)


class TodoPage(Page):
    title = "To-do"

    def __init__(self):
        super().__init__()
        row = QHBoxLayout()
        self.entry = QLineEdit(placeholderText="Add a task and press Enter")
        self.entry.returnPressed.connect(self._add)
        row.addWidget(self.entry, 1)
        row.addWidget(button("Add", "Primary", self._add))
        row.addWidget(button("Clear completed", cb=self._clear_done))
        self.root.addLayout(row)
        self.list = _DeletableList(self._delete)
        self.list.itemChanged.connect(self._changed)
        self.root.addWidget(self.list, 1)
        self.root.addWidget(label("Tick items to complete them. Select one and press Delete to remove it.", "Faint"))
        self._loading = False

    def _add(self):
        text = self.entry.text().strip()
        if text:
            actions.run("todo_add", {"items": [text]})
            self.entry.clear()
            self.refresh()

    def _clear_done(self):
        actions.run("todo_remove", {"clear_done": True})
        self.refresh()

    def _delete(self, item):
        from ..skills.productivity import todos
        idx = item.data(Qt.UserRole)
        with todos as data:
            if 0 <= idx < len(data["items"]):
                data["items"].pop(idx)
        self.refresh()

    def _changed(self, item):
        if self._loading:
            return
        from ..skills.productivity import todos
        idx = item.data(Qt.UserRole)
        with todos as data:
            if 0 <= idx < len(data["items"]):
                data["items"][idx]["done"] = item.checkState() == Qt.Checked
                data["items"][idx]["done_at"] = time.time()
        QTimer.singleShot(250, self.refresh)

    def refresh(self):
        from ..skills.productivity import todos
        self._loading = True
        self.list.clear()
        items = list(enumerate(todos.data.get("items", [])))
        items.sort(key=lambda p: (p[1].get("done", False), -p[1].get("created", 0) if p[1].get("done") else 0))
        for idx, it in items:
            li = QListWidgetItem(it["text"])
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            li.setCheckState(Qt.Checked if it.get("done") else Qt.Unchecked)
            li.setData(Qt.UserRole, idx)
            if it.get("done"):
                f = li.font()
                f.setStrikeOut(True)
                li.setFont(f)
                li.setForeground(QColor(125, 108, 158))
            self.list.addItem(li)
        self._loading = False


class RoutinesPage(Page):
    title = "Routines & macros"

    def __init__(self):
        super().__init__()
        self.root.addWidget(label("One phrase runs a list of commands, written the way you'd say them. You can also "
                                  "say: “create a routine called wind down that pauses the music and turns on "
                                  "dark mode”.", "Muted", wrap=True))
        body = QHBoxLayout()
        body.setSpacing(16)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setFixedWidth(230)
        self.list.currentRowChanged.connect(self._select)
        left.addWidget(self.list, 1)
        left.addWidget(button("New routine", cb=self._new))
        body.addLayout(left)

        f, lay = card_frame()
        lay.addWidget(label("NAME", "Section"))
        self.name = QLineEdit(placeholderText="e.g. study mode")
        lay.addWidget(self.name)
        lay.addWidget(label("ALSO TRIGGERED BY", "Section"))
        self.phrases = QLineEdit(placeholderText="comma separated, e.g. time to study, start studying")
        lay.addWidget(self.phrases)
        lay.addWidget(label("STEPS, ONE PER LINE", "Section"))
        self.steps = QPlainTextEdit()
        self.steps.setPlaceholderText("close fortnite\nopen google classroom\nstart a focus session")
        lay.addWidget(self.steps, 1)
        lay.addWidget(label("One step per line. A step can be any Gem command, or: wait 2 seconds · wait for discord · "
                            "switch to discord · type hello · press ctrl+k · click the send button · "
                            "click at 45% 60% in discord · ask me first. Macros you record (“record a macro”) and "
                            "ones Gem works out for you (“figure out how to …”) show up here too. Big steps, like "
                            "sending a message or pressing Enter in a chat, always wait for your “send it”.", "Faint",
                            wrap=True))
        row = QHBoxLayout()
        self.feedback = label("", "Faint")
        row.addWidget(self.feedback, 1)
        row.addWidget(button("Delete", "Danger", self._delete))
        row.addWidget(button("Run now", cb=self._run))
        row.addWidget(button("Save", "Primary", self._save))
        lay.addLayout(row)
        body.addWidget(f, 1)
        self.root.addLayout(body, 1)
        self._routines = []

    def refresh(self):
        from ..skills import routines
        current = self.name.text().strip().lower()
        self._routines = routines.all_routines()
        self.list.blockSignals(True)
        self.list.clear()
        for r in self._routines:
            self.list.addItem(r["name"].capitalize())
        self.list.blockSignals(False)
        names = [r["name"] for r in self._routines]
        if current in names:
            self.list.setCurrentRow(names.index(current))
        elif self._routines:
            self.list.setCurrentRow(0)
        else:
            self._new()

    def _select(self, row):
        if 0 <= row < len(self._routines):
            r = self._routines[row]
            self.name.setText(r["name"])
            self.phrases.setText(", ".join(r.get("phrases", [])))
            self.steps.setPlainText("\n".join(r.get("steps", [])))
            self.feedback.setText("")

    def _new(self):
        self.list.clearSelection()
        self.name.clear()
        self.phrases.clear()
        self.steps.clear()
        self.name.setFocus()

    def _save(self):
        steps = [l.strip() for l in self.steps.toPlainText().splitlines() if l.strip()]
        phrases = [p.strip() for p in self.phrases.text().split(",") if p.strip()]
        from ..actions import ActionError
        from ..skills import routines
        try:
            res = routines.save(self.name.text(), steps, phrases)     # typed here by you: runs without asking first
        except ActionError as e:
            res = str(e)
        self.feedback.setText(str(res or ""))
        self.refresh()

    def _delete(self):
        if self.name.text().strip():
            self.feedback.setText(str(actions.run("routine_delete", {"name": self.name.text()}) or ""))
            self._new()
            self.refresh()

    def _run(self):
        name = self.name.text().strip()
        if name and svc.assistant:
            svc.assistant.submit_text("run " + name)
            self.feedback.setText("Running %s…" % name)


class NotesPage(Page):
    title = "Notes"

    def __init__(self):
        super().__init__()
        self.edit = QPlainTextEdit()
        self.edit.setFont(T.font(14))
        self.root.addWidget(self.edit, 1)
        row = QHBoxLayout()
        self.saved = label("", "Faint")
        row.addWidget(self.saved)
        row.addStretch()
        row.addWidget(button("Save", "Primary", self.save))
        self.root.addLayout(row)

    def refresh(self):
        text = ""
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                text = f.read()
        self.edit.setPlainText(text)
        self.saved.setText("Say “take a note that…” to add notes by voice.")

    def save(self):
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            f.write(self.edit.toPlainText())
        self.saved.setText("Saved.")

    def hideEvent(self, e):
        if self.edit.document().isModified():
            self.save()
        super().hideEvent(e)


class MemoryPage(Page):
    title = "Memory"

    def __init__(self):
        super().__init__()
        self.root.addWidget(label("Things Gem remembers about you and uses in every conversation.", "Muted"))
        row = QHBoxLayout()
        self.entry = QLineEdit(placeholderText="e.g. My school email is …")
        self.entry.returnPressed.connect(self._add)
        row.addWidget(self.entry, 1)
        row.addWidget(button("Remember", "Primary", self._add))
        self.root.addLayout(row)
        self.table = table(["Fact", ""], stretch=0)
        self.root.addWidget(self.table, 1)

    def _add(self):
        if self.entry.text().strip():
            actions.run("remember", {"fact": self.entry.text().strip()})
            self.entry.clear()
            self.refresh()

    def _delete(self, fact):
        from ..skills.productivity import memory
        with memory as data:
            data["facts"] = [f for f in data["facts"] if f != fact]
        self.refresh()

    def refresh(self):
        from ..skills.productivity import memory
        facts = memory.data.get("facts") or []
        self.table.setRowCount(0)          # drop old cell widgets right away
        self.table.setRowCount(len(facts))
        for r, fact in enumerate(facts):
            self.table.setItem(r, 0, QTableWidgetItem(fact))
            self.table.setCellWidget(r, 1, cell_button("Forget", lambda _=False, f=fact: self._delete(f)))


class HistoryPage(Page):
    title = "History"

    def __init__(self):
        super().__init__()
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        self.root.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addWidget(label("Stored only on this PC.", "Faint"))
        row.addStretch()
        row.addWidget(button("Clear history", "Danger", self._clear))
        self.root.addLayout(row)

    def _clear(self):
        try:
            os.remove(HISTORY_FILE)
        except OSError:
            pass
        self.refresh()

    def refresh(self):
        entries = history_entries(300)
        if not entries:
            self.view.setHtml("<p style='color:#9b88bf'>Nothing yet.</p>")
            return
        parts = ["<style>p{margin:0 0 2px 0}</style>"]
        last_day = None
        for e in reversed(entries):
            dt = datetime.datetime.fromtimestamp(e.get("t", 0))
            day = dt.strftime("%A %d %B")
            if day != last_day:
                parts.append("<p style='color:#a07cc8;font-size:11px;font-weight:600;margin-top:14px'>%s</p>"
                             % day.upper())
                last_day = day
            src = {"ptt": "\U0001F399", "typed": "⌨", "open": "\U0001F442"}.get(e.get("source"), "")
            parts.append("<p style='color:#7d6c9e;font-size:12px;margin-top:10px'>%s %s</p>"
                         % (dt.strftime("%I:%M %p").lstrip("0"), src))
            if e.get("you"):
                parts.append("<p style='color:#b9a8d9'><i>“%s”</i></p>" % html.escape(e["you"]))
            parts.append("<p style='color:#ece3fb'>%s</p>" % html.escape(e.get("gem") or "Done."))
        self.view.setHtml("".join(parts))


# ── Settings ─────────────────────────────────────────────────────────────────

VOICES = [("Ava (US, natural)", "en-US-AvaMultilingualNeural"), ("Emma (US)", "en-US-EmmaMultilingualNeural"),
          ("Jenny (US)", "en-US-JennyNeural"), ("Aria (US)", "en-US-AriaNeural"),
          ("Andrew (US, male)", "en-US-AndrewMultilingualNeural"), ("Brian (US, male)", "en-US-BrianMultilingualNeural"),
          ("Sonia (UK)", "en-GB-SoniaNeural"), ("Libby (UK)", "en-GB-LibbyNeural"),
          ("Natasha (Australia)", "en-AU-NatashaNeural"), ("Neerja (India)", "en-IN-NeerjaExpressiveNeural")]

# (section, label, path, kind, options, needs restart)
FIELDS = [
    ("You", "Your name", "user_name", "text", None, False),
    ("You", "Home city (weather, briefings)", "home_city", "text", None, False),
    ("You", "Away note ({name} and {when} are filled in)", "away_message", "text", None, False),
    ("Voice", "Engine", "voice.engine", "choice", [("On this PC: instant, same voice always", "piper"),
                                                  ("Online Microsoft voices: richer, can lag", "edge"),
                                                  ("Old Windows voices", "sapi")], False),
    ("Voice", "Voice on this PC", "voice.piper_voice", "choice", PIPER_VOICES, False),
    ("Voice", "Online voice", "voice.edge_voice", "choice", VOICES, False),
    ("Voice", "Speed", "voice.rate", "choice", [("Slower", "-10%"), ("Normal", "+0%"), ("A bit faster", "+5%"),
                                                ("Faster", "+15%"), ("Fastest", "+25%")], False),
    ("Voice", "Volume", "voice.volume", "slider", (30, 100), False),
    ("Voice", "Speak during calls", "voice.speak_in_calls", "bool", None, False),
    ("Voice", "Speak in gaming mode", "voice.speak_in_gaming", "bool", None, False),
    ("Look & sound", "Show the island when Gem is idle", "appearance.island_when_idle", "bool", None, False),
    ("Look & sound", "Hide the island in fullscreen video and games", "appearance.hide_in_fullscreen", "bool", None, False),
    ("Look & sound", "How long answers stay on screen", "appearance.card_seconds", "choice",
     [("Short", 0.7), ("Normal", 1.0), ("Long", 1.5), ("Extra long", 2.2)], False),
    ("Look & sound", "Sound cues when listening starts and stops", "sounds.cues", "bool", None, False),
    ("Look & sound", "Outline what Gem talks about on screen", "appearance.screen_highlights", "bool", None, False),
    ("Look & sound", "Alarm and reminder sounds", "reminders.alarm_sound", "bool", None, False),
    ("Look & sound", "Keyboard light animation", "lights.animate", "bool", None, False),
    ("Look & sound", "Flash keyboard lights for alerts", "lights.flash_on_alerts", "bool", None, False),
    ("Listening", "Follow-up window in always-listening (seconds)", "listening.conversation_window", "int", (5, 120), False),
    ("Listening", "Microphone", "listening.input_device", "mic", None, True),
    ("Listening", "Speech detection strictness", "listening.vad_aggressiveness", "choice",
     [("Relaxed", 1), ("Normal", 2), ("Strict (noisy rooms)", 3)], True),
    ("Listening", "Detect calls automatically", "calls.auto_detect", "bool", None, True),
    ("Listening", "Voice lock strictness (only respond to your voice)", "voice_lock.threshold", "choice",
     [("Relaxed", 0.38), ("Normal", 0.45), ("Strict", 0.52)], False),
    ("Listening", "Keep learning my voice from push-to-talk", "voice_lock.learn_from_push_to_talk", "bool", None, False),
    ("Listening", "Voice lock while holding Caps Lock too", "voice_lock.in_push_to_talk", "bool", None, False),
    ("Listening", "Auto-clip hype moments in games", "auto_clip.enabled", "bool", None, False),
    ("Keys", "Hold time before Caps Lock counts as held (ms)", "keys.hold_ms", "int", (120, 600), True),
    ("Keys", "Triple-tap window (ms)", "keys.triple_tap_ms", "int", (400, 1500), True),
    ("Keys", "Command bar hotkey", "keys.command_bar", "text", None, True),
    ("Keys", "Panic hotkey", "keys.panic", "text", None, True),
    ("Productivity", "Break reminder every (minutes, 0 = off)", "reminders.break_minutes", "int", (0, 240), False),
    ("Productivity", "Break reminder message", "reminders.break_message", "text", None, False),
    ("Productivity", "Focus session length (minutes)", "focus.work_minutes", "int", (5, 180), False),
    ("Productivity", "Focus break length (minutes)", "focus.break_minutes", "int", (1, 60), False),
    ("Productivity", "Default quiet time (minutes)", "snooze_minutes", "int", (1, 240), False),
    ("AI", "Models, in order of preference", "ai.models", "list", None, False),
    ("AI", "Reasoning effort", "ai.reasoning_effort", "choice", [("Low (fastest)", "low"), ("Medium", "medium"),
                                                                ("High", "high")], False),
    ("Panic hotkey", "Apps to close", "panic.close_apps", "list", None, False),
    ("Panic hotkey", "Website to open", "panic.open_url", "text", None, False),
    ("Panic hotkey", "Voice phrases that trigger it", "panic.voice_phrases", "list", None, False),
]


def _get(cfg, path):
    cur = cfg
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set(cfg, path, value):
    parts = path.split(".")
    cur = cfg
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


class MapEditor(QWidget):
    """Two-column editor for the apps / websites maps."""

    def __init__(self, key, left, right):
        super().__init__()
        self.key = key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([left, right])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setMinimumHeight(220)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(button("Add row", cb=lambda: self.table.insertRow(self.table.rowCount())))
        row.addWidget(button("Remove selected", cb=lambda: self.table.removeRow(self.table.currentRow())))
        row.addStretch()
        lay.addLayout(row)

    def load(self, mapping):
        self.table.setRowCount(0)
        for k, v in sorted((mapping or {}).items()):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(k))
            self.table.setItem(r, 1, QTableWidgetItem(v if isinstance(v, str) else ", ".join(v)))

    def value(self):
        out = {}
        for r in range(self.table.rowCount()):
            k, v = self.table.item(r, 0), self.table.item(r, 1)
            if k and v and k.text().strip():
                out[k.text().strip().lower()] = v.text().strip()
        return out


class SettingsPage(Page):
    title = "Settings"

    def __init__(self):
        super().__init__()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("Root")
        self.form = QVBoxLayout(body)
        self.form.setContentsMargins(0, 0, 12, 0)
        self.form.setSpacing(16)
        scroll.setWidget(body)
        self.root.addWidget(scroll, 1)
        self.widgets = {}

        sections = {}
        for section, name, path, kind, opts, restart in FIELDS:
            if section not in sections:
                f, lay = card_frame()
                lay.addWidget(label(section.upper(), "Section"))
                sections[section] = lay
                self.form.addWidget(f)
            row = QHBoxLayout()
            text = name + ("  ↻" if restart else "")
            l = label(text)
            if restart:
                l.setToolTip("Applies after restarting Gem")
            row.addWidget(l, 1)
            w = self._make(kind, opts)
            self.widgets[path] = (kind, w, restart)
            row.addWidget(w)
            if path in ("voice.piper_voice", "voice.edge_voice"):
                row.addWidget(button("Test", cb=lambda _=False, p=path: self._test_voice(p)))
            sections[section].addLayout(row)

        f, lay = card_frame()
        lay.addWidget(label("STARTUP", "Section"))
        row = QHBoxLayout()
        row.addWidget(label("Start Gem when Windows starts"), 1)
        self.startup = Toggle()
        row.addWidget(self.startup)
        lay.addLayout(row)
        self.form.addWidget(f)

        f, lay = card_frame()
        lay.addWidget(label("APP NAMES", "Section"))
        lay.addWidget(label("Extra names for apps. The value can be an exe path or a Start Menu name. "
                            "Installed apps are found automatically.", "Faint", wrap=True))
        self.apps = MapEditor("apps", "Say", "Opens")
        lay.addWidget(self.apps)
        self.form.addWidget(f)

        f, lay = card_frame()
        lay.addWidget(label("WEBSITES", "Section"))
        self.sites = MapEditor("websites", "Say", "URL")
        lay.addWidget(self.sites)
        self.form.addWidget(f)
        self.form.addStretch()

        bar = QHBoxLayout()
        self.note = label("↻ = applies after restart", "Faint")
        bar.addWidget(self.note)
        bar.addStretch()
        bar.addWidget(button("Open settings file", cb=lambda: os.startfile(SETTINGS_FILE)))
        bar.addWidget(button("Restart Gem", cb=self._restart))
        bar.addWidget(button("Save", "Primary", self._save))
        self.root.addLayout(bar)

    def _make(self, kind, opts):
        if kind == "bool":
            return Toggle()
        if kind == "int":
            s = QSpinBox()
            s.setRange(*opts)
            s.setFixedWidth(110)
            return s
        if kind == "slider":
            s = QSlider(Qt.Horizontal)
            s.setRange(*opts)
            s.setFixedWidth(200)
            return s
        if kind in ("choice", "mic"):
            c = QComboBox()
            c.setFixedWidth(260)
            if kind == "choice":
                for name, val in opts:
                    c.addItem(name, val)
            return c
        e = QLineEdit()
        e.setFixedWidth(300 if kind == "text" else 380)
        if kind == "list":
            e.setPlaceholderText("comma separated")
        return e

    def _fill_mics(self, combo, current):
        combo.clear()
        combo.addItem("Windows default", "")
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            seen = set()
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0 and info.get("hostApi") == 0 and info["name"] not in seen:
                    seen.add(info["name"])
                    combo.addItem(info["name"], info["name"])
            pa.terminate()
        except Exception:
            pass
        if current and combo.findData(current) < 0:
            combo.addItem(current, current)
        combo.setCurrentIndex(max(0, combo.findData(current)))

    def refresh(self):
        cfg = svc.config
        for path, (kind, w, _) in self.widgets.items():
            val = _get(cfg, path)
            if kind == "bool":
                w.setChecked(bool(val))
            elif kind == "int":
                w.setValue(int(val or 0))
            elif kind == "slider":
                w.setValue(int(round(float(val or 0.9) * 100)))
            elif kind == "mic":
                self._fill_mics(w, val or "")
            elif kind == "choice":
                idx = w.findData(val)
                if idx < 0 and val is not None:
                    w.addItem(str(val), val)
                    idx = w.count() - 1
                w.setCurrentIndex(max(0, idx))
            elif kind == "list":
                w.setText(", ".join(val or []))
            else:
                w.setText(str(val or ""))
        from .tray import startup_enabled
        self.startup.setChecked(startup_enabled())
        self.apps.load(cfg.get("apps"))
        self.sites.load(cfg.get("websites"))
        self.note.setText("↻ = applies after restart")

    def _collect(self):
        new = json.loads(json.dumps(svc.config))
        for path, (kind, w, _) in self.widgets.items():
            if kind == "bool":
                val = w.isChecked()
            elif kind == "int":
                val = w.value()
            elif kind == "slider":
                val = round(w.value() / 100.0, 2)
            elif kind in ("choice", "mic"):
                val = w.currentData()
            elif kind == "list":
                val = [x.strip() for x in w.text().split(",") if x.strip()]
            else:
                val = w.text().strip()
            _set(new, path, val)
        new["apps"] = self.apps.value()
        new["websites"] = self.sites.value()
        return new

    def _save(self):
        old = json.loads(json.dumps(svc.config))
        new = self._collect()
        restart = [p for p, (_, _, r) in self.widgets.items() if r and _get(old, p) != _get(new, p)]
        Dashboard.apply_settings(new)
        try:
            from .tray import set_startup, startup_enabled
            if self.startup.isChecked() != startup_enabled():
                set_startup(self.startup.isChecked())
        except Exception as e:
            log.error("Startup toggle failed: %s", e)
        self.note.setText("Saved. Restart Gem to apply the ↻ changes." if restart else "Saved.")

    def _test_voice(self, path):
        """Use the chosen voice right away (Save keeps it) and say a sample once it's ready."""
        if not svc.voice:
            return
        cfg = svc.voice.cfg
        for p in ("voice.piper_voice", "voice.edge_voice", "voice.rate", "voice.volume"):
            kind, w, _ = self.widgets[p]
            cfg[p.split(".")[1]] = round(w.value() / 100.0, 2) if kind == "slider" else w.currentData()
        cfg["engine"] = "piper" if path == "voice.piper_voice" else "edge"
        self.widgets["voice.engine"][1].setCurrentIndex(self.widgets["voice.engine"][1].findData(cfg["engine"]))
        self.note.setText("Loading the voice…" if cfg["engine"] == "piper" else "")
        svc.voice.preview("Hi, I'm Gem. This is how I sound.")

    def _restart(self):
        self._save()
        from ..app import restart
        restart()


# ── Window ───────────────────────────────────────────────────────────────────

class Dashboard(QMainWindow):
    PAGES = [("home", "Home", HomePage), ("reminders", "Reminders", RemindersPage), ("classes", "Classes", ClassesPage),
             ("todo", "To-do", TodoPage), ("routines", "Routines && macros", RoutinesPage),       # && shows one &
             ("notes", "Notes", NotesPage),
             ("memory", "Memory", MemoryPage),
             ("history", "History", HistoryPage), ("settings", "Settings", SettingsPage)]

    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.setWindowTitle("Gem")
        self.setWindowIcon(QIcon(QPixmap.fromImage(render_image(128))))
        self.resize(1040, 720)
        self.setMinimumSize(880, 580)
        self.setStyleSheet(QSS)

        root = QWidget()
        root.setObjectName("Root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 18)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        brand.addWidget(CrystalLogo(46))
        brand.addWidget(label("Gem", "Brand"))
        brand.addStretch()
        sl.addLayout(brand)
        sl.addSpacing(14)
        self.stack = QStackedWidget()
        self.nav = QButtonGroup(self)
        self.pages = {}
        for key, name, cls in self.PAGES:
            b = button(name, "Nav")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.open_page(k, focus=False))
            self.nav.addButton(b)
            sl.addWidget(b)
            page = cls()
            self.pages[key] = (b, page)
            self.stack.addWidget(page)
        sl.addStretch()
        sl.addWidget(label("Hold Caps Lock to talk", "Faint"))
        h.addWidget(side)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    def open_page(self, key, focus=True):
        if key not in self.pages:
            key = "home"
        b, page = self.pages[key]
        b.setChecked(True)
        self.stack.setCurrentWidget(page)
        try:
            page.refresh()
            page.tick()
        except Exception:
            log.exception("Refreshing %s failed", key)
        if focus:
            if self.isMinimized():
                self.showNormal()
            self.show()
            _dark_titlebar(self)
            self.raise_()
            self.activateWindow()
            try:
                from ..winapi import focus_window
                focus_window(int(self.winId()))
            except Exception:
                pass

    def _tick(self):
        if not self.isVisible():
            return
        self._ticks = getattr(self, "_ticks", 0) + 1
        page = self.stack.currentWidget()
        try:
            page.tick()
            if isinstance(page, HomePage) and self._ticks % 4 == 0:
                page.refresh()
        except Exception:
            log.exception("Dashboard tick failed")

    # ── Settings persistence ─────────────────────────────────────────────────

    @staticmethod
    def save_settings():
        try:
            _write_json(SETTINGS_FILE, svc.config)
        except Exception as e:
            log.error("Could not save settings: %s", e)

    @staticmethod
    def apply_settings(new):
        """Update the live config in place (so every module sees it) and save."""
        def merge(old, upd):
            for k, v in upd.items():
                if isinstance(v, dict) and isinstance(old.get(k), dict) and k not in ("apps", "websites", "processes"):
                    merge(old[k], v)
                else:
                    old[k] = v
        merge(svc.config, new)
        st = svc.state
        st.speak_in_calls = svc.config["voice"].get("speak_in_calls", False)
        st.speak_in_gaming = svc.config["voice"].get("speak_in_gaming", False)
        st.conversation_window = svc.config["listening"].get("conversation_window", 25)
        if svc.lights:
            svc.lights.animate = svc.config["lights"].get("animate", True)
        Dashboard.save_settings()
