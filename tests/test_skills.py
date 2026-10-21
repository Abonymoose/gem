"""Skills whose logic can be checked without a PC: the timeline, ambient sound routing, reminders."""
import threading
import time
import unittest

from . import svc  # noqa: F401  (sets up the test environment)
from .test_router import route
from gem.skills import ambient, timeline


class AmbientRoutingTest(unittest.TestCase):
    def tearDown(self):
        ambient.player["stop"] = None

    def test_stop_the_sounds(self):
        # Gem itself says "say stop the sounds when you're done".
        for said in ("stop the sounds", "stop sounds", "stop the rain sounds", "turn off the white noise",
                     "stop the noise"):
            with self.subTest(said=said):
                self.assertEqual(route(said).action, "ambient_stop")

    def test_while_playing(self):
        ambient.player["stop"] = threading.Event()
        self.assertEqual(route("stop the rain").action, "ambient_stop")
        self.assertEqual(route("turn off the fan").action, "ambient_stop")
        m = route("make it quieter")
        self.assertEqual((m.action, m.args), ("ambient_volume", {"direction": "down"}))
        self.assertEqual(route("make the rain a bit louder").args, {"direction": "up"})

    def test_when_nothing_plays(self):
        self.assertIsNone(route("stop the rain"))
        m = route("make it quieter")
        self.assertEqual((m.action, m.args), ("volume", {"change": -10}))


class TimelineTest(unittest.TestCase):
    def setUp(self):
        self._saved = (timeline._open, list(timeline._closed), dict(timeline.store.data), timeline._restored[0])
        timeline._restored[0] = True
        timeline.store.data = {"days": {}, "open": None}
        timeline._closed[:] = []
        self.now = time.time()

    def tearDown(self):
        timeline._open, timeline._closed[:], timeline.store.data, timeline._restored[0] = self._saved

    def seg(self, app, start_min_ago, end_min_ago):
        return {"s": self.now - start_min_ago * 60, "e": self.now - end_min_ago * 60, "app": app, "titles": []}

    def test_session_since_last_break(self):
        timeline._closed[:] = [self.seg("Chrome", 300, 200),            # then a 20 minute break
                               self.seg("Discord", 180, 120),
                               self.seg("Chrome", 118, 60)]             # a 2 minute gap isn't a break
        timeline._open = self.seg("Valorant", 59, 0)
        start = timeline.session_start(self.now)
        self.assertAlmostEqual(start, self.now - 180 * 60, delta=1)
        self.assertIn("3 hours", timeline.pc_session())

    def test_away(self):
        timeline._closed[:] = [self.seg("Chrome", 60, 30)]
        timeline._open = None
        self.assertIsNone(timeline.session_start(self.now))

    def test_how_long_playing_uses_current_app(self):
        timeline._open = self.seg("Valorant", 45, 0)
        m = route("how long have I been playing")
        self.assertEqual((m.action, m.args), ("timeline_app", {"app": "", "which": "current"}))
        self.assertIn("Valorant", timeline.timeline_app(**m.args))

    def test_routes(self):
        self.assertEqual(route("how long have I been on the computer").action, "pc_session")
        self.assertEqual(route("when did I last take a break").action, "pc_session")
        self.assertEqual(route("how long have I been playing Valorant").args["app"], "valorant")


if __name__ == "__main__":
    unittest.main()
