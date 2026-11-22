"""Google Calendar from its iCal link: a weekly class with a skipped and a moved week, an all-day event, an event
in UTC, the day's answer, what's next, and the heads-up before an event. The download is faked."""
import datetime
import unittest
from unittest import mock

from . import svc  # noqa: F401  (sets up the test environment)
from .test_router import route
from gem.actions import ActionError
from gem.skills import gcal

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
X-WR-TIMEZONE:Asia/Kolkata
BEGIN:VEVENT
UID:a
SUMMARY:Science class
DTSTART;TZID=Asia/Kolkata:20261102T093000
DTEND;TZID=Asia/Kolkata:20261102T103000
RRULE:FREQ=WEEKLY;BYDAY=MO
EXDATE;TZID=Asia/Kolkata:20261116T093000
END:VEVENT
BEGIN:VEVENT
UID:a
RECURRENCE-ID;TZID=Asia/Kolkata:20261123T093000
SUMMARY:Science class (moved)
DTSTART;TZID=Asia/Kolkata:20261123T113000
DTEND;TZID=Asia/Kolkata:20261123T123000
END:VEVENT
BEGIN:VEVENT
UID:b
SUMMARY:PTM
DTSTART:20261123T093000Z
DTEND:20261123T103000Z
END:VEVENT
BEGIN:VEVENT
UID:c
SUMMARY:Sports day
DTSTART;VALUE=DATE:20261123
DTEND;VALUE=DATE:20261124
END:VEVENT
BEGIN:VEVENT
UID:d
SUMMARY:Called off
STATUS:CANCELLED
DTSTART;TZID=Asia/Kolkata:20261123T170000
DTEND;TZID=Asia/Kolkata:20261123T180000
END:VEVENT
END:VCALENDAR
"""
MONDAY_8AM = datetime.datetime(2026, 11, 23, 8, 0)


class CalendarTest(unittest.TestCase):
    def setUp(self):
        gcal._cal.update(data=None, feed="", soon=None)
        gcal._warned.clear()
        self.feed = {"feed": "webcal://calendar.google.com/secret/basic.ics", "remind_minutes": 10}
        self.get = mock.Mock(return_value=mock.Mock(content=ICS, raise_for_status=lambda: None))
        for p in [mock.patch.object(gcal, "cfg", lambda: self.feed), mock.patch.object(gcal.requests, "get", self.get),
                  mock.patch.object(gcal.nettime, "now", return_value=MONDAY_8AM)]:
            p.start()
            self.addCleanup(p.stop)

    def test_today(self):
        res = gcal.calendar_events("today")
        self.assertEqual(str(res), "Today you have Sports day all day, then Science class (moved) at 11:30 AM, "
                                   "then PTM at 3:00 PM.")                     # cancelled one left out; UTC -> IST
        self.assertTrue(self.get.call_args[0][0].startswith("https://"))     # webcal:// fetched over https
        self.assertEqual([r["next"] for r in res.card["rows"]], [False, True, False])

    def test_skipped_week_and_next(self):
        gcal._ready()
        week_before = datetime.datetime(2026, 11, 16)
        self.assertEqual(gcal.events(week_before, week_before + datetime.timedelta(days=1)), [])
        self.assertIn("Science class (moved), at 11:30 AM", str(gcal.calendar_events("next")))

    def test_heads_up_once_and_island(self):
        gcal._ready()
        with mock.patch.object(gcal, "notify") as notify:
            gcal.heads_up(datetime.datetime(2026, 11, 23, 11, 20, 5))
            gcal.heads_up(datetime.datetime(2026, 11, 23, 11, 20, 40))      # the same minute again: no repeat
        notify.assert_called_once_with("Science class (moved)", "Science class (moved) starts in 10 minutes.",
                                       sound="soft")
        with mock.patch.object(gcal.nettime, "now", return_value=datetime.datetime(2026, 11, 23, 11, 21)):
            self.assertEqual(gcal.upcoming(15)[0], "Science class (moved)")

    def test_not_connected(self):
        self.feed = {"feed": ""}
        with self.assertRaisesRegex(ActionError, "isn't connected"):
            gcal.calendar_events()

    def test_commands(self):
        self.assertEqual(route("what's on my calendar tomorrow").args, {"day": "tomorrow"})
        self.assertEqual(route("when's my next event").args, {"day": "next"})
        self.assertEqual(route("when's my next class").action, "next_class")


if __name__ == "__main__":
    unittest.main()
