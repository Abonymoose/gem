"""Gem's crystal eye, drawn with Pillow for the tray icon."""
import math

from PIL import Image, ImageDraw


def make_icon(size=64, dim=False):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size // 2
    r = int(size * 0.42)
    op = 0.82
    verts = [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90)))
             for i in range(6)]
    fills = ["#2e1f4a", "#1a1228"] * 3
    strokes = ["#a07cc8", "#c4a0f0"] * 3 if not dim else ["#5a4a70", "#6a5a80"] * 3
    for i in range(6):
        v0, v1 = verts[i], verts[(i + 1) % 6]
        mx, my = (v0[0] + v1[0] + cx) / 3, (v0[1] + v1[1] + cy) / 3
        dx, dy = mx - cx, my - cy
        dist = max(1, math.hypot(dx, dy))
        push = op * size * 0.12
        px, py = dx / dist * push, dy / dist * push
        d.polygon([v0[0] + px, v0[1] + py, v1[0] + px, v1[1] + py, cx + px * 0.2, cy + py * 0.2],
                  fill=fills[i], outline=strokes[i])
    er = int(size * 0.22)
    d.ellipse([cx - er, cy - int(er * 0.65), cx + er, cy + int(er * 0.65)], fill="#1a1228")
    ir = int(er * 0.78)
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill="#4a2d7a" if not dim else "#3a3048")
    ir2 = int(er * 0.52)
    d.ellipse([cx - ir2, cy - ir2, cx + ir2, cy + ir2], fill="#2e1f4a")
    pr = int(er * 0.35)
    d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill="#0d0a14")
    s = max(1, int(pr * 0.55))
    d.ellipse([cx + int(pr * 0.2), cy - int(pr * 0.8), cx + int(pr * 0.2) + s, cy - int(pr * 0.8) + s],
              fill="#d4b8f0")
    return img.convert("RGB")
