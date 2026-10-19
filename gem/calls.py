"""Call detection: another app using the microphone means you're on a call.

Windows records which apps are using the mic in the registry (the same data
behind the mic icon in the taskbar). Discord voice, Teams, Zoom, Meet in the
browser and in-game voice chat all show up here.
"""
import logging
import sys
import threading
import time
import winreg

from .runtime import caption, svc

log = logging.getLogger("gem.calls")

_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"


def _in_use(key):
    try:
        stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")
        start, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")
        return stop == 0 and start > 0
    except OSError:
        return False


def mic_users():
    users = []
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY)
    except OSError:
        return users

    def walk(parent, prefix=""):
        i = 0
        while True:
            try:
                name = winreg.EnumKey(parent, i)
            except OSError:
                return
            i += 1
            try:
                with winreg.OpenKey(parent, name) as sub:
                    if name == "NonPackaged":
                        walk(sub, "")
                    elif _in_use(sub):
                        users.append(name.replace("#", "\\"))
            except OSError:
                pass

    with root:
        walk(root)
    return users


def _pretty(app_id):
    base = app_id.rsplit("\\", 1)[-1]
    base = base.split("_", 1)[0] if "\\" not in app_id else base
    return base.replace(".exe", "").replace(".EXE", "")


class CallWatcher:
    def __init__(self, cfg):
        self.cfg = cfg
        own = sys.executable.lower()
        self.ignore = [s.lower() for s in cfg.get("ignore_apps", [])] + [own]

    def start(self):
        if self.cfg.get("auto_detect", True):
            threading.Thread(target=self._run, name="calls", daemon=True).start()

    def active_call_apps(self):
        return [u for u in mic_users() if not any(ig in u.lower() for ig in self.ignore)]

    def _run(self):
        while True:
            try:
                apps = self.active_call_apps()
                in_call = bool(apps)
                st = svc.state
                if in_call != st.in_call:
                    name = _pretty(apps[0]) if apps else ""
                    st.update(in_call=in_call, call_app=name)
                    if in_call:
                        log.info("Call detected (%s)", apps[0])
                        svc.voice.stop()
                        caption("On a call with %s. I'll stay quiet; hold Caps Lock to talk to me." % name, seconds=5)
                    else:
                        log.info("Call ended")
                        caption("Call ended.", seconds=3)
            except Exception:
                log.exception("Call check failed")
            time.sleep(2)
