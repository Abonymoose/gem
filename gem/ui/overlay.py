"""The animated crystal in the corner, captions, and the type-a-command bar.

Tk lives on the main thread. Other threads talk to it only through
self._inbox, which the animation loop drains every frame.
"""
import ctypes
import logging
import math
import queue
import random
import time
import tkinter as tk

from ..config import runtime
from ..runtime import svc

log = logging.getLogger("gem.overlay")

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

_user32 = ctypes.windll.user32
_user32.GetAncestor.restype = ctypes.c_void_p
_user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]


def _set_exstyle(widget, add):
    hwnd = _user32.GetAncestor(widget.winfo_id(), 2)    # GA_ROOT
    style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | add)
    return hwnd


class GemOverlay:
    SIZE = 60
    MARGIN = 16
    C_BG = "#0d0a14"
    C_SHADOW = "#1a1228"
    C_DEEP = "#2e1f4a"
    C_MID = "#4a2d7a"
    C_IRIS = "#6b3fa0"
    C_LAVENDER = "#a07cc8"
    C_HIGHLIGHT = "#d4b8f0"
    C_FF = ["#c4a0f0", "#a07cc8", "#d4b8f0", "#8b5cbf", "#b890e8", "#c4a0f0"]

    CAPTION_BG = "#151022"
    CAPTION_BORDER = "#3b2a5c"
    CAPTION_TEXT = "#ece3fb"
    CAPTION_YOU = "#9b88bf"

    def __init__(self, show_crystal=True):
        self._inbox = queue.Queue()
        self.show_crystal = show_crystal
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#010101")
        self.root.configure(bg="#010101")
        self.root.resizable(False, False)

        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        pos = runtime.data.get("overlay_pos")
        if pos and 0 <= pos[0] < sw - 20 and 0 <= pos[1] < sh - 20:
            x, y = pos
        else:
            x, y = sw - self.SIZE - self.MARGIN, sh - self.SIZE - self.MARGIN - 40
        self.root.geometry("%dx%d+%d+%d" % (self.SIZE, self.SIZE, x, y))

        self.canvas = tk.Canvas(self.root, width=self.SIZE, height=self.SIZE, bg="#010101", highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind("<Button-3>", self._context_menu)

        self._build_caption()
        self._build_command_bar()

        self.tick = 0
        self.started = time.time()
        self.shard_open = 0.0
        self.eye_lx = self.eye_ly = 0.0
        self.portal_a1 = self.portal_a2 = 0.0
        self.void_angle = 0.0
        self.scope_angle = 0.0
        self.gaming_zoom = 0.0
        self.ff = self._init_ff()
        self._drag = None
        self._caption_until = 0.0
        self._you_text = ""
        self._gem_text = ""
        self._visible = None

        self.root.update_idletasks()
        _set_exstyle(self.root, WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        self.root.after(1000, self._keep_on_top)
        self._animate()

    # ── Thread-safe API ──────────────────────────────────────────────────────

    def caption(self, gem=None, you=None, seconds=None):
        self._inbox.put(("caption", (gem, you, seconds)))

    def open_command_bar(self):
        self._inbox.put(("command_bar", None))

    def quit(self):
        self._inbox.put(("quit", None))

    def run(self):
        self.root.mainloop()

    # ── Captions ─────────────────────────────────────────────────────────────

    def _build_caption(self):
        self.cap = tk.Toplevel(self.root)
        self.cap.withdraw()
        self.cap.overrideredirect(True)
        self.cap.attributes("-topmost", True)
        self.cap.attributes("-alpha", 0.95)
        frame = tk.Frame(self.cap, bg=self.CAPTION_BG, highlightbackground=self.CAPTION_BORDER,
                         highlightthickness=1, padx=12, pady=8)
        frame.pack(fill="both", expand=True)
        self.cap_you = tk.Label(frame, text="", fg=self.CAPTION_YOU, bg=self.CAPTION_BG, justify="left",
                                anchor="w", wraplength=340, font=("Segoe UI", 9, "italic"))
        self.cap_gem = tk.Label(frame, text="", fg=self.CAPTION_TEXT, bg=self.CAPTION_BG, justify="left",
                                anchor="w", wraplength=340, font=("Segoe UI", 10))
        self.cap_you.pack(fill="x")
        self.cap_gem.pack(fill="x")
        self.cap.update_idletasks()
        _set_exstyle(self.cap, WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_LAYERED)

    def _show_caption(self, gem, you, seconds):
        if you is not None:
            self._you_text = you
            if gem is None:
                self._gem_text = ""
        if gem is not None:
            self._gem_text = gem
        self.cap_you.configure(text=('"%s"' % self._you_text) if self._you_text else "")
        self.cap_gem.configure(text=self._gem_text)
        if self._you_text:
            self.cap_you.pack(fill="x")
        else:
            self.cap_you.pack_forget()
        if self._gem_text:
            self.cap_gem.pack(fill="x")
        else:
            self.cap_gem.pack_forget()
        if seconds is None:
            seconds = max(3.5, len(self._gem_text) / 12.0) if self._gem_text else 8.0
        self._caption_until = time.time() + seconds
        self.cap.update_idletasks()
        w, h = self.cap.winfo_reqwidth(), self.cap.winfo_reqheight()
        ox, oy = self.root.winfo_x(), self.root.winfo_y()
        x = ox - w - 10
        if x < 0:
            x = ox + self.SIZE + 10
        y = max(0, oy + self.SIZE - h)
        self.cap.geometry("+%d+%d" % (x, y))
        if not svc.state.hidden:
            self.cap.deiconify()
            self.cap.lift()

    def _hide_caption(self):
        self._you_text = self._gem_text = ""
        self.cap.withdraw()

    # ── Command bar ──────────────────────────────────────────────────────────

    def _build_command_bar(self):
        self.bar = tk.Toplevel(self.root)
        self.bar.withdraw()
        self.bar.overrideredirect(True)
        self.bar.attributes("-topmost", True)
        frame = tk.Frame(self.bar, bg=self.CAPTION_BG, highlightbackground=self.C_LAVENDER,
                         highlightthickness=1, padx=10, pady=8)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Gem", fg=self.C_LAVENDER, bg=self.CAPTION_BG,
                 font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 8))
        self.entry = tk.Entry(frame, width=48, bg="#1f1830", fg=self.CAPTION_TEXT, insertbackground=self.CAPTION_TEXT,
                              relief="flat", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.entry.bind("<Return>", self._submit_command)
        self.entry.bind("<Escape>", lambda e: self._close_command_bar())
        self.bar.bind("<FocusOut>", lambda e: self.root.after(150, self._maybe_close_bar))

    def _open_command_bar(self):
        self.bar.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = self.bar.winfo_reqwidth()
        self.bar.geometry("+%d+%d" % ((sw - w) // 2, sh - 180))
        self.bar.deiconify()
        self.bar.lift()
        self.entry.delete(0, "end")
        try:
            from ..winapi import focus_window
            focus_window(_user32.GetAncestor(self.bar.winfo_id(), 2))
        except Exception:
            pass
        self.bar.focus_force()
        self.entry.focus_set()

    def _maybe_close_bar(self):
        if self.bar.focus_get() is None:
            self._close_command_bar()

    def _close_command_bar(self):
        self.bar.withdraw()

    def _submit_command(self, _event=None):
        text = self.entry.get().strip()
        self._close_command_bar()
        if text and svc.assistant:
            svc.assistant.submit_text(text)

    # ── Mouse ────────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y(), e.x_root, e.y_root)

    def _drag_move(self, e):
        if self._drag:
            dx, dy = self._drag[0], self._drag[1]
            self.root.geometry("+%d+%d" % (e.x_root - dx, e.y_root - dy))

    def _drag_end(self, e):
        if not self._drag:
            return
        moved = abs(e.x_root - self._drag[2]) + abs(e.y_root - self._drag[3]) > 3
        self._drag = None
        if moved:
            with runtime as data:
                data["overlay_pos"] = [self.root.winfo_x(), self.root.winfo_y()]
        else:
            self._open_command_bar()

    def _context_menu(self, e):
        from .. import actions
        from ..state import ALWAYS_LISTENING, PUSH_TO_TALK
        st = svc.state
        m = tk.Menu(self.root, tearoff=0, bg=self.CAPTION_BG, fg=self.CAPTION_TEXT,
                    activebackground=self.C_DEEP, activeforeground=self.CAPTION_TEXT)
        mode = tk.StringVar(value=st.mode)
        m.add_radiobutton(label="Push to talk", variable=mode, value=PUSH_TO_TALK,
                          command=lambda: actions.run("set_mode", {"mode": PUSH_TO_TALK}))
        m.add_radiobutton(label="Always listening", variable=mode, value=ALWAYS_LISTENING,
                          command=lambda: actions.run("set_mode", {"mode": ALWAYS_LISTENING}))
        m.add_separator()
        if st.snoozed:
            m.add_command(label="Resume", command=lambda: actions.run("resume"))
        else:
            m.add_command(label="Quiet for 10 minutes", command=lambda: actions.run("snooze", {"minutes": 10}))
            m.add_command(label="Quiet for 1 hour", command=lambda: actions.run("snooze", {"minutes": 60}))
        m.add_command(label="Type a command…", command=self._open_command_bar)
        m.add_separator()
        m.add_command(label="Quit Gem", command=lambda: svc.assistant.quit())
        m.tk_popup(e.x_root, e.y_root)

    # ── Animation ────────────────────────────────────────────────────────────

    def _keep_on_top(self):
        self.root.attributes("-topmost", True)
        self.root.after(2000, self._keep_on_top)

    def _init_ff(self):
        cx = cy = self.SIZE // 2
        dots = []
        for i in range(10):
            a, dist = random.uniform(0, 2 * math.pi), random.uniform(4, 22)
            dots.append({"x": cx + math.cos(a) * dist, "y": cy + math.sin(a) * dist,
                         "vx": random.uniform(-0.3, 0.3), "vy": random.uniform(-0.3, 0.3),
                         "r": random.uniform(1, 2.5), "phase": random.uniform(0, 2 * math.pi),
                         "speed": random.uniform(0.04, 0.09), "color": self.C_FF[i % len(self.C_FF)]})
        return dots

    def _hex_pts(self, cx, cy, r, offset=0):
        pts = []
        for i in range(6):
            a = math.radians(60 * i + offset)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        return pts

    def _visual(self):
        st = svc.state
        if time.time() - self.started < 3.0:
            return "launch"
        if st.gaming:
            return "gaming"
        if st.ruhig:
            return "glitch"
        if st.snoozed:
            return "sleeping"
        if st.speaking:
            return "speaking"
        if st.thinking:
            return "thinking"
        if st.ears_open():
            return "listening"
        return "idle"

    def _draw_launch(self):
        cx = cy = self.SIZE // 2
        for d in self.ff:
            d["x"] += d["vx"]
            d["y"] += d["vy"]
            if math.hypot(d["x"] - cx, d["y"] - cy) > 24:
                d["vx"] *= -0.7
                d["vy"] *= -0.7
            d["vx"] = max(-0.5, min(0.5, d["vx"] + random.uniform(-0.04, 0.04)))
            d["vy"] = max(-0.5, min(0.5, d["vy"] + random.uniform(-0.04, 0.04)))
            alpha = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(self.tick * d["speed"] + d["phase"]))
            r = d["r"] * alpha
            self.canvas.create_oval(d["x"] - r, d["y"] - r, d["x"] + r, d["y"] + r, fill=d["color"], outline="")

    def _draw_crystal(self, open_amount):
        c = self.canvas
        cx = cy = self.SIZE // 2
        r = 26
        verts = [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90)))
                 for i in range(6)]
        fills = [self.C_DEEP, self.C_SHADOW] * 3
        for i in range(6):
            v0, v1 = verts[i], verts[(i + 1) % 6]
            mx, my = (v0[0] + v1[0] + cx) / 3, (v0[1] + v1[1] + cy) / 3
            dx, dy = mx - cx, my - cy
            dist = max(1, math.hypot(dx, dy))
            push = open_amount * 7
            px, py = dx / dist * push, dy / dist * push
            c.create_polygon([v0[0] + px, v0[1] + py, v1[0] + px, v1[1] + py, cx + px * 0.2, cy + py * 0.2],
                             fill=fills[i], outline=self.C_LAVENDER, width=1)

    def _draw_eye(self, alpha=1.0, level=0.0):
        c = self.canvas
        cx = cy = self.SIZE // 2
        t = self.tick
        er = int(13 * alpha)
        if er < 2:
            return
        c.create_oval(cx - er, cy - int(er * 0.65), cx + er, cy + int(er * 0.65), fill=self.C_SHADOW, outline="")
        ir = max(1, int(er * 0.78))
        c.create_oval(cx - ir, cy - ir, cx + ir, cy + ir, fill=self.C_MID, outline="")
        ir2 = max(1, int(er * (0.52 + 0.2 * level)))
        c.create_oval(cx - ir2, cy - ir2, cx + ir2, cy + ir2, fill=self.C_DEEP, outline="")
        self.eye_lx += (5 * math.sin(t * 0.04) - self.eye_lx) * 0.08
        self.eye_ly += (3 * math.cos(t * 0.031) - self.eye_ly) * 0.08
        pr = max(1, int(er * (0.35 - 0.12 * level)))
        px, py = cx + self.eye_lx * alpha * (1 - level), cy + self.eye_ly * alpha * (1 - level)
        c.create_oval(px - pr, py - pr, px + pr, py + pr, fill=self.C_BG, outline="")
        s = max(1, int(pr * 0.55))
        c.create_oval(px + pr * 0.2, py - pr * 0.8, px + pr * 0.2 + s, py - pr * 0.8 + s,
                      fill=self.C_HIGHLIGHT, outline="")

    def _draw_portal(self):
        c = self.canvas
        cx = cy = self.SIZE // 2
        t = self.tick
        self.portal_a1 = (self.portal_a1 + 1.2) % 360
        self.portal_a2 = (self.portal_a2 - 0.8) % 360
        c.create_polygon(self._hex_pts(cx, cy, 26, self.portal_a1), fill="", outline=self.C_IRIS, width=1)
        c.create_polygon(self._hex_pts(cx, cy, 19, self.portal_a2), fill="", outline=self.C_LAVENDER, width=1)
        gr = 13 + 1.5 * math.sin(t * 0.07)
        c.create_oval(cx - gr, cy - gr, cx + gr, cy + gr, fill=self.C_DEEP, outline="")
        ir = int(12 * (0.92 + 0.08 * math.sin(t * 0.06)))
        c.create_oval(cx - ir, cy - ir, cx + ir, cy + ir, fill=self.C_MID, outline="")
        c.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill=self.C_DEEP, outline="")
        self.eye_lx += (5 * math.sin(t * 0.035) - self.eye_lx) * 0.06
        self.eye_ly += (4 * math.cos(t * 0.028) - self.eye_ly) * 0.06
        px, py = cx + self.eye_lx, cy + self.eye_ly
        c.create_oval(px - 4, py - 4, px + 4, py + 4, fill=self.C_BG, outline="")
        c.create_oval(px + 0.5, py - 2.5, px + 2.5, py - 0.5, fill=self.C_HIGHLIGHT, outline="")

    def _draw_sleeping(self):
        c = self.canvas
        cx = cy = self.SIZE // 2
        t = self.tick
        c.create_polygon(self._hex_pts(cx, cy, 28, 0), fill=self.C_BG, outline=self.C_SHADOW, width=1)
        stars = [(-22, -14, "#a07cc8", 0.0, 1.0), (-10, -20, "#6b3fa0", 0.8, 0.7), (2, -17, "#c4a0f0", 1.6, 1.2),
                 (15, -19, "#8b5cbf", 2.4, 0.7), (23, -5, "#d4b8f0", 3.2, 1.0), (-20, 12, "#6b3fa0", 3.9, 0.7),
                 (0, 16, "#a07cc8", 1.2, 0.8), (20, 17, "#c4a0f0", 1.9, 1.0), (-7, -6, "#4a2d7a", 0.6, 0.6),
                 (12, 5, "#6b3fa0", 2.8, 0.6)]
        for i, j in [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (4, 7), (5, 6), (6, 7), (2, 8), (8, 9)]:
            c.create_line(cx + stars[i][0], cy + stars[i][1], cx + stars[j][0], cy + stars[j][1],
                          fill=self.C_DEEP, width=1)
        for sx, sy, col, phase, size in stars:
            r = max(0.5, size * (0.2 + 0.8 * (0.5 + 0.5 * math.sin(t * 0.025 + phase))))
            c.create_oval(cx + sx - r, cy + sy - r, cx + sx + r, cy + sy + r, fill=col, outline="")
        er = 10
        c.create_oval(cx - er, cy - int(er * 0.6), cx + er, cy + int(er * 0.6), fill=self.C_SHADOW, outline="")
        c.create_line(cx - er, cy, cx + er, cy, fill=self.C_LAVENDER, width=1)

    def _draw_glitch(self):
        c = self.canvas
        cx = cy = self.SIZE // 2
        self._draw_crystal(0.0)
        blocks = [(cx - 18, cy - 10, cx - 4, cy - 7, self.C_LAVENDER), (cx + 2, cy - 8, cx + 12, cy - 5, self.C_HIGHLIGHT),
                  (cx - 14, cy + 2, cx + 2, cy + 5, self.C_IRIS), (cx + 4, cy + 8, cx + 16, cy + 11, self.C_LAVENDER),
                  (cx - 10, cy - 2, cx + 4, cy + 1, self.C_HIGHLIGHT), (cx - 6, cy + 14, cx + 8, cy + 17, self.C_IRIS)]
        for i, (x1, y1, x2, y2, col) in enumerate(blocks):
            if (self.tick + i * 7) % 8 < 5:
                o = random.randint(-2, 2)
                c.create_rectangle(x1 + o, y1, x2 + o, y2, fill=col, outline="")
        for i in range(3):
            if (self.tick + i * 11) % 15 < 8:
                y = cy - 12 + i * 10
                c.create_line(cx - 22, y, cx + 22, y, fill=self.C_LAVENDER, width=1)

    def _draw_thinking(self):
        c = self.canvas
        cx = cy = self.SIZE // 2
        self.void_angle = (self.void_angle + 4) % 360
        self._draw_crystal(0.35)
        for r, col, speed in [(20, self.C_IRIS, 1), (14, self.C_LAVENDER, -1.5)]:
            a = math.radians(self.void_angle * speed)
            c.create_line(cx, cy, cx + r * math.cos(a), cy + r * math.sin(a), fill=col, width=1)
            c.create_line(cx, cy, cx + r * math.cos(a + math.pi * 0.8), cy + r * math.sin(a + math.pi * 0.8),
                          fill=col, width=1)
        c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=self.C_BG, outline="")

    def _draw_gaming(self):
        c = self.canvas
        cx = cy = self.SIZE // 2
        self.gaming_zoom = min(1.0, self.gaming_zoom + 0.016)
        outer_r, mid_r = int(26 - self.gaming_zoom * 5), int(18 - self.gaming_zoom * 3)
        self.scope_angle += 0.4
        a = math.radians(self.scope_angle)
        c.create_polygon(self._hex_pts(cx, cy, 28, 0), fill=self.C_BG, outline=self.C_DEEP, width=1)
        c.create_oval(cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r, fill="", outline=self.C_IRIS, width=1)
        c.create_oval(cx - mid_r, cy - mid_r, cx + mid_r, cy + mid_r, fill="", outline=self.C_LAVENDER, width=1)
        for off in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
            ang = a + off
            c.create_line(cx + math.cos(ang) * (mid_r + 2), cy + math.sin(ang) * (mid_r + 2),
                          cx + math.cos(ang) * outer_r, cy + math.sin(ang) * outer_r, fill=self.C_LAVENDER, width=1)
            c.create_line(cx + math.cos(ang) * 3, cy + math.sin(ang) * 3, cx + math.cos(ang) * (mid_r - 3),
                          cy + math.sin(ang) * (mid_r - 3), fill=self.C_HIGHLIGHT, width=1)
        r = 2 + math.sin(self.tick * 0.08) * 1.5
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=self.C_HIGHLIGHT, outline="")

    def _draw_badges(self):
        st = svc.state
        if st.in_call:
            r = 3 + 0.6 * math.sin(self.tick * 0.08)
            self.canvas.create_oval(51 - r, 8 - r, 51 + r, 8 + r, fill=self.C_HIGHLIGHT, outline=self.C_DEEP)
        if st.mode == "always_listening" and not st.ears_open() and not st.snoozed:
            self.canvas.create_line(6, 54, 14, 46, fill=self.C_LAVENDER, width=2)

    def _drain_inbox(self):
        while True:
            try:
                kind, arg = self._inbox.get_nowait()
            except queue.Empty:
                return
            if kind == "caption":
                self._show_caption(*arg)
            elif kind == "command_bar":
                self._open_command_bar()
            elif kind == "quit":
                self.root.quit()
                return

    def _animate(self):
        try:
            self._drain_inbox()
            visible = self.show_crystal and not svc.state.hidden
            if visible != self._visible:
                self._visible = visible
                if visible:
                    self.root.deiconify()
                else:
                    self.root.withdraw()
                    self.cap.withdraw()
            if self._caption_until and time.time() > self._caption_until:
                self._caption_until = 0.0
                self._hide_caption()
            if visible:
                self._frame()
        except Exception:
            log.exception("Overlay frame failed")
        self.root.after(33, self._animate)

    def _frame(self):
        self.canvas.delete("all")
        self.tick += 1
        s = self._visual()
        if s == "launch":
            self._draw_launch()
        elif s == "sleeping":
            self._draw_sleeping()
        elif s == "glitch":
            self._draw_glitch()
        elif s == "thinking":
            self._draw_thinking()
        elif s == "gaming":
            self._draw_gaming()
        elif s == "speaking":
            self.shard_open += (0.0 - self.shard_open) * 0.1
            self._draw_portal()
        elif s == "listening":
            self.shard_open += (0.9 - self.shard_open) * 0.25
            self._draw_crystal(self.shard_open)
            level = svc.listener.level if (svc.listener and svc.state.key_held) else 0.0
            self._draw_eye(min(1.0, max(0.0, (self.shard_open - 0.2) / 0.5)), level=min(1.0, level * 2.5))
        else:
            self.shard_open += (0.0 - self.shard_open) * 0.2
            self._draw_crystal(self.shard_open)
            if self.shard_open > 0.2:
                self._draw_eye(min(1.0, (self.shard_open - 0.2) / 0.5))
        self._draw_badges()
