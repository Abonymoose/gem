"""Audio ducking: other apps get quieter while you talk to Gem or she talks back.

Each app's own volume is lowered to a fraction and restored exactly afterwards.
All Windows audio calls run on one worker thread, so they never block the UI,
the keyboard hook or the voice.
"""
import logging
import os
import queue
import threading
import time

log = logging.getLogger("gem.ducking")


class Ducker:
    def __init__(self, cfg):
        self.cfg = cfg
        self._reasons = set()
        self._saved = {}             # pid -> original volume
        self._q = queue.Queue()
        threading.Thread(target=self._run, name="ducking", daemon=True).start()

    def duck(self, reason):
        self._q.put(("duck", reason))

    def unduck(self, reason, delay=0.0):
        if delay:
            threading.Timer(delay, lambda: self._q.put(("unduck", reason))).start()
        else:
            self._q.put(("unduck", reason))

    def release_all(self, timeout=1.5):
        """Restore every app's volume now (used when Gem quits)."""
        done = threading.Event()
        self._reasons.clear()
        self._q.put(("unduck", None))
        self._q.put(("signal", done))
        done.wait(timeout)

    def _run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        while True:
            kind, reason = self._q.get()
            try:
                if kind == "signal":
                    reason.set()
                    continue
                if kind == "duck":
                    was_ducked = bool(self._reasons)
                    self._reasons.add(reason)
                    if not was_ducked and self.cfg.get("duck_others", True):
                        self._lower()
                else:
                    self._reasons.discard(reason)
                    if not self._reasons:
                        self._restore()
            except Exception:
                log.debug("Ducking failed", exc_info=True)

    def _sessions(self):
        from pycaw.pycaw import AudioUtilities
        me = os.getpid()
        return [s for s in AudioUtilities.GetAllSessions() if s.Process and s.Process.pid != me]

    def _lower(self):
        factor = float(self.cfg.get("duck_level", 0.3))
        for s in self._sessions():
            if s.State != 1:                     # only apps actually playing sound
                continue
            v = s.SimpleAudioVolume
            cur = v.GetMasterVolume()
            if cur > 0.05:
                self._saved[s.Process.pid] = cur
                self._fade(v, cur, cur * factor)

    def _restore(self):
        if not self._saved:
            return
        for s in self._sessions():
            orig = self._saved.get(s.Process.pid)
            if orig is not None:
                v = s.SimpleAudioVolume
                self._fade(v, v.GetMasterVolume(), orig)
        self._saved.clear()

    @staticmethod
    def _fade(vol, start, end, steps=6, dur=0.18):
        for i in range(1, steps + 1):
            vol.SetMasterVolume(max(0.0, min(1.0, start + (end - start) * i / steps)), None)
            time.sleep(dur / steps)
