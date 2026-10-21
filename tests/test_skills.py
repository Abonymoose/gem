"""Skills whose logic can be checked without a PC: the timeline, ambient sound routing, reminders."""
import datetime
import threading
import time
import unittest

from . import svc  # noqa: F401  (sets up the test environment)
from .test_router import route
from gem import router
from gem.config import runtime
from gem.skills import ambient, timeline, timers

NOW = datetime.datetime(2026, 10, 21, 20, 15)       # a Wednesday evening


class RepeatingReminderTest(unittest.TestCase):
    def parse(self, said):
        msg, at, every = timers.parse_repeat(router.normalize(said)[0], NOW)
        return msg, at.strftime("%a %H:%M") if at else None, every

    def test_parse(self):
        cases = {
            "remind me to drink water every hour": ("drink water", None, 60),
            "remind me every 30 minutes to stretch": ("stretch", None, 30),
            "remind me to stretch every half hour": ("stretch", None, 30),
            "remind me hourly to drink water": ("drink water", None, 60),
            "remind me to take my meds every day at 9 am": ("take your meds", "Thu 09:00", 1440),
            "every morning remind me to check my email": ("check your email", "Thu 08:00", 1440),
            "remind me every night to set an alarm": ("set an alarm", "Wed 21:00", 1440),
            "remind me to call grandma every sunday": ("call grandma", "Sun 09:00", 10080),
            "remind me to take out the trash every monday at 7 pm": ("take out the trash", "Mon 19:00", 10080),
            "remind me to water the plants every 2 days": ("water the plants", None, 2880),
        }
        for said, expected in cases.items():
            with self.subTest(said=said):
                self.assertEqual(self.parse(said), expected)

    def test_not_repeating(self):
        self.assertIsNone(timers.parse_repeat("remind me to check every file in 10 minutes", NOW))
        m = route("remind me to check every file in 10 minutes")
        self.assertEqual(m.args["message"], "check every file")
        self.assertNotIn("repeat_minutes", m.args)

    def test_routes(self):
        m = route("remind me to drink water every hour")
        self.assertEqual((m.action, m.args["repeat_minutes"], m.args["message"]), ("set_reminder", 60, "drink water"))

    def test_keeps_its_slot(self):
        nine = datetime.datetime(2026, 10, 21, 9, 0)
        item = {"at": nine.timestamp(), "repeat_minutes": 1440}
        # Went off late at 11:20 (PC was asleep): tomorrow is still 9:00.
        self.assertEqual(timers.next_repeat(item, nine.replace(hour=11, minute=20)), nine + datetime.timedelta(days=1))
        # Gem was off for three days: the next 9:00 after now.
        self.assertEqual(timers.next_repeat(item, nine + datetime.timedelta(days=3, hours=1)),
                         nine + datetime.timedelta(days=4))
        hourly = {"at": nine.timestamp(), "repeat_minutes": 60}
        self.assertEqual(timers.next_repeat(hourly, nine), nine + datetime.timedelta(hours=1))

    def test_every_phrase(self):
        self.assertEqual(timers.every_phrase(60), "hour")
        self.assertEqual(timers.every_phrase(30), "30 minutes")
        self.assertEqual(timers.every_phrase(1440), "day")
        self.assertEqual(timers.every_phrase(2880), "2 days")
        self.assertEqual(timers.every_phrase(90), "1 hour and 30 minutes")

    def test_set_and_list(self):
        reply = timers.set_reminder("drink water", repeat_minutes=60)
        self.assertIn("every hour", reply)
        try:
            self.assertIn("a reminder to drink water every hour, next at", timers.list_timers())
        finally:
            timers.cancel_timer("drink water", kind="reminder")
        self.assertNotIn("drink water", timers.list_timers())


class TimerControlsTest(unittest.TestCase):
    def setUp(self):
        timers.cancel_timer(all=True)
        with runtime as data:
            data.pop("timer_lengths", None)

    tearDown = setUp

    def test_nothing_running(self):
        self.assertIsNone(route("5 more minutes"))
        self.assertIsNone(route("pause the timer"))

    def test_more_time_pause_resume(self):
        timers.set_timer(minutes=10, label="pasta")
        self.assertEqual(route("5 more minutes").args, {"seconds": 300})
        self.assertEqual(route("another minute").args, {"seconds": 60})
        self.assertFalse(route("5 more minutes").safe)                  # "I need 5 more minutes" to someone
        self.assertNotEqual(getattr(route("remind me in 5 more minutes"), "action", None), "timer_adjust")
        self.assertEqual(route("take 2 minutes off the timer").args, {"seconds": -120, "label": ""})
        self.assertEqual(route("add 5 minutes to the pasta timer").args, {"seconds": 300, "label": "pasta"})

        self.assertIn("15 minutes left", timers.timer_adjust(300))
        self.assertEqual(route("pause the timer").action, "timer_pause")
        self.assertIsNone(route("resume the timer"))                    # nothing paused yet
        self.assertIn("Paused the pasta timer", timers.timer_pause(True))
        t = timers._timer()
        self.assertTrue(timers.paused(t))
        frozen = timers.remaining(t)
        self.assertGreater(t["at"], time.time() + 365 * 86400)          # parked: it can't go off while paused
        self.assertIn("paused with", timers.list_timers())
        self.assertIn("already paused", timers.timer_pause(True))
        self.assertEqual(route("resume the timer").args, {"pause": False, "label": ""})
        timers.timer_pause(False)
        t = timers._timer()
        self.assertFalse(timers.paused(t))
        self.assertAlmostEqual(t["at"] - time.time(), frozen, delta=2)

    def test_remembers_lengths(self):
        self.assertIsNone(route("set a pasta timer"))                   # never used: the AI asks how long
        timers.set_timer(minutes=12, label="pasta")
        timers.cancel_timer(all=True)
        for said in ("set a pasta timer", "pasta timer", "set a timer for pasta"):
            with self.subTest(said=said):
                self.assertEqual(route(said).args, {"label": "pasta"})
        self.assertIn("12 minute timer for pasta", timers.set_timer(label="pasta"))

    def test_cancel_by_name(self):
        self.assertEqual(route("cancel the pasta timer").args["match"], "pasta")
        self.assertEqual(route("stop the 10 minute timer").args["match"], "")
        self.assertTrue(route("cancel both timers").args["all"])


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
