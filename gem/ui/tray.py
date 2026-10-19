"""System tray icon and menu."""
import logging
import os
import sys
import threading

from .. import actions
from ..config import DATA_DIR, LOG_FILE, NOTES_FILE, SETTINGS_FILE
from ..runtime import svc
from ..state import ALWAYS_LISTENING, PUSH_TO_TALK
from .icon import make_icon

log = logging.getLogger("gem.tray")

# The Run key rather than a Startup-folder shortcut: Store Python can't write
# real files into AppData (see config.py), but registry writes go through.
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command():
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "gem2.py"))
    return '"%s" "%s"' % (pyw if os.path.exists(pyw) else exe, script)


def startup_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, "Gem")
            return True
    except OSError:
        return False


def set_startup(enabled):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, "Gem", 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, "Gem")
            except OSError:
                pass


class Tray:
    def __init__(self):
        self.icon = None
        try:
            import pystray
            self.pystray = pystray
        except ImportError:
            self.pystray = None
            log.warning("pystray not installed; no tray icon")

    def start(self):
        if not self.pystray:
            return
        p = self.pystray
        Item, Menu = p.MenuItem, p.Menu
        st = svc.state

        def run(name, **args):
            return lambda: actions.run(name, args)

        menu = Menu(
            Item(lambda _: "Gem · " + st.describe(), None, enabled=False),
            Menu.SEPARATOR,
            Item("Push to talk", run("set_mode", mode=PUSH_TO_TALK), checked=lambda _: st.mode == PUSH_TO_TALK, radio=True),
            Item("Always listening", run("set_mode", mode=ALWAYS_LISTENING),
                 checked=lambda _: st.mode == ALWAYS_LISTENING, radio=True),
            Menu.SEPARATOR,
            Item("Quiet for 10 minutes", run("snooze", minutes=10), visible=lambda _: not st.snoozed),
            Item("Quiet for 1 hour", run("snooze", minutes=60), visible=lambda _: not st.snoozed),
            Item("Resume", run("resume"), visible=lambda _: st.snoozed),
            Item("Voice replies", lambda: actions.run("voice_replies", {"on": not st.voice_enabled}),
                 checked=lambda _: st.voice_enabled),
            Item("Gaming mode", lambda: actions.run("gaming_mode", {"on": not st.gaming}), checked=lambda _: st.gaming),
            Item("Show overlay", lambda: st.update(hidden=not st.hidden), checked=lambda _: not st.hidden),
            Menu.SEPARATOR,
            Item("Type a command…", lambda: svc.overlay and svc.overlay.open_command_bar()),
            Item("Open notes", lambda: os.startfile(NOTES_FILE) if os.path.exists(NOTES_FILE) else actions.run("notes_open")),
            Item("Settings", lambda: os.startfile(SETTINGS_FILE)),
            Item("Data folder", lambda: os.startfile(DATA_DIR)),
            Item("Log", lambda: os.startfile(LOG_FILE)),
            Item("Start with Windows", lambda: self._toggle_startup(), checked=lambda _: startup_enabled()),
            Menu.SEPARATOR,
            Item("Quit", lambda: svc.assistant.quit()),
        )
        self.icon = p.Icon("Gem", make_icon(), "Gem · " + st.describe(), menu=menu)
        st.subscribe(self._on_state)
        threading.Thread(target=self.icon.run, name="tray", daemon=True).start()

    def _toggle_startup(self):
        try:
            set_startup(not startup_enabled())
        except Exception as e:
            log.error("Startup toggle failed: %s", e)
        self.refresh()

    def _on_state(self, st, changed):
        if set(changed) & {"mode", "snoozed_until", "in_call", "gaming", "voice_enabled", "hidden", "focus_until"}:
            self.refresh()

    def refresh(self):
        if not self.icon:
            return
        try:
            self.icon.title = ("Gem · " + svc.state.describe())[:127]
            self.icon.update_menu()
        except Exception:
            pass

    def notify(self, title, message):
        if not self.icon:
            return
        try:
            self.icon.notify(message[:250], title)
        except Exception as e:
            log.debug("Tray notification failed: %s", e)

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
