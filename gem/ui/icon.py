"""Tray icon image: the same crystal the overlay draws, as a Pillow image."""
from PIL import Image
from PySide6.QtGui import QImage

from .crystal import render_image


def make_icon(size=64):
    img = render_image(size, "idle").convertToFormat(QImage.Format_RGBA8888)
    data = bytes(img.constBits())
    return Image.frombuffer("RGBA", (img.width(), img.height()), data, "raw", "RGBA", img.bytesPerLine(), 1).copy()
