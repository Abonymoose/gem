"""Icon images: the same crystal the island draws, as Pillow images.

Regenerate the exe icon after changing the crystal:
    python -c "from gem.ui.icon import write_ico; write_ico('gem.ico')"
"""
from PIL import Image
from PySide6.QtGui import QImage

from .crystal import render_image

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _pil(qimg):
    img = qimg.convertToFormat(QImage.Format_RGBA8888)
    data = bytes(img.constBits())
    return Image.frombuffer("RGBA", (img.width(), img.height()), data, "raw", "RGBA", img.bytesPerLine(), 1).copy()


def make_icon(size=64):
    return _pil(render_image(size))


def write_ico(path):
    """Write a multi-size .ico, each size rendered on its own so small ones stay crisp."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])   # noqa: F841 (fonts/painting need an app)
    images = [_pil(render_image(s)) for s in ICO_SIZES]
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES], append_images=images[:-1])
