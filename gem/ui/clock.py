"""Gem's clock: a small always-on-top window with the real time (from the internet, see nettime), for when the PC's
own clock is off. Drag it anywhere; double-click or Esc closes it."""
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import nettime
from . import theme as T


class ClockWindow(QWidget):
    W, H = 300, 132

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Gem clock")
        self.resize(self.W, self.H)
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.right() - self.W - 24, area.top() + 72)         # top right, under the island
        self._grab = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(250)

    def paintEvent(self, _):
        now = nettime.now()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(8, 8, self.W - 16, self.H - 16)
        p.setBrush(T.ISLAND)
        p.setPen(QPen(T.alpha(T.SOFT, 0.35), 1.2))
        p.drawRoundedRect(box, 22, 22)
        p.setPen(T.TEXT)
        p.setFont(T.font(36, QFont.DemiBold))
        p.drawText(QRectF(8, 14, box.width(), 50), Qt.AlignCenter, now.strftime("%I:%M:%S %p").lstrip("0"))
        p.setPen(T.TEXT_DIM)
        p.setFont(T.font(13))
        p.drawText(QRectF(8, 64, box.width(), 22), Qt.AlignCenter, now.strftime("%A, %d %B %Y").replace(" 0", " "))
        p.setPen(T.alpha(T.SOFT, 0.75))
        p.setFont(T.font(11))
        p.drawText(QRectF(8, 90, box.width(), 20), Qt.AlignCenter, nettime.status())
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._grab = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._grab is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._grab)

    def mouseReleaseEvent(self, e):
        self._grab = None

    def mouseDoubleClickEvent(self, e):
        self.hide()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
