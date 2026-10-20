"""Colours and fonts shared by every Gem window."""
from PySide6.QtGui import QColor, QFont

BG = QColor(13, 10, 20)
SHADOW = QColor(26, 18, 40)
DEEP = QColor(46, 31, 74)
MID = QColor(74, 45, 122)
IRIS = QColor(107, 63, 160)
VIOLET = QColor(139, 92, 191)
LAVENDER = QColor(160, 124, 200)
SOFT = QColor(196, 160, 240)
HIGHLIGHT = QColor(212, 184, 240)

CARD_TOP = QColor(30, 22, 50, 246)
CARD_BOTTOM = QColor(18, 13, 32, 246)
CARD_BORDER = QColor(196, 160, 240, 46)
TEXT = QColor(240, 234, 252)
TEXT_DIM = QColor(176, 160, 206)
TEXT_FAINT = QColor(132, 116, 164)

# Island glow / waveform gradient stops (cycled).
GLOW = [QColor(139, 92, 246), QColor(236, 72, 153), QColor(96, 165, 250), QColor(196, 160, 240)]

ISLAND = QColor(0, 0, 0, 252)
ISLAND_EDGE = QColor(255, 255, 255, 16)

FAMILY = "Segoe UI"


def font(px, weight=QFont.Normal, italic=False, family=FAMILY):
    f = QFont(family)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    f.setItalic(italic)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def alpha(color, a):
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return QColor(int(c1.red() + (c2.red() - c1.red()) * t), int(c1.green() + (c2.green() - c1.green()) * t),
                  int(c1.blue() + (c2.blue() - c1.blue()) * t), int(c1.alpha() + (c2.alpha() - c1.alpha()) * t))
