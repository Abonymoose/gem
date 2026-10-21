import datetime
import unittest

from . import svc  # noqa: F401  (sets up the test environment)
from gem.parse import duration_phrase, normalize_time_words, parse_duration, parse_percent, parse_when, \
    words_to_numbers
from gem.skills.calc import calculate, convert

NOW = datetime.datetime(2026, 10, 21, 20, 15)       # a Wednesday evening


def when(text):
    dt, _ = parse_when(text, NOW)
    return dt.strftime("%a %H:%M") if dt else None


class NumbersTest(unittest.TestCase):
    def test_words_to_numbers(self):
        cases = {
            "twenty five minutes": "25 minutes",
            "two thirty": "2 30",                       # a time, not 32
            "five five": "5 5",
            "half an hour": "30 minutes",
            "an hour and a half": "90 minutes",
            "a few minutes": "3 minutes",
            "a hundred and one dalmatians": "101 dalmatians",
            "two thousand five hundred": "2500",
            "1.5 million": "1500000",
            "three and four": "3 and 4",                # "and" between numbers stays a sum
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(words_to_numbers(spoken), expected)

    def test_durations(self):
        self.assertEqual(parse_duration("1 hour 20 minutes"), 4800)
        self.assertEqual(parse_duration("ninety seconds"), 90)
        self.assertEqual(parse_duration("2 and a half hours"), 9000)
        self.assertIsNone(parse_duration("no time at all"))
        self.assertEqual(duration_phrase(3660), "1 hour and 1 minute")
        self.assertEqual(duration_phrase(45), "45 seconds")

    def test_percent(self):
        self.assertEqual(parse_percent("forty percent"), 40)
        self.assertIsNone(parse_percent("200"))


class WhenTest(unittest.TestCase):
    def test_times(self):
        cases = {
            "in 10 minutes": "Wed 20:25",
            "in an hour and a half": "Wed 21:45",
            "at 7": "Thu 07:00",                        # the next 7 o'clock
            "at 10 pm": "Wed 22:00",
            "at 6:30 pm": "Thu 18:30",                  # already past today
            "tomorrow at 8 am": "Thu 08:00",
            "tonight at 9": "Wed 21:00",
            "on friday at noon": "Fri 12:00",
            "midnight": "Thu 00:00",
            "at 12 am": "Thu 00:00",
            "19:55": "Thu 19:55",
            "tomorrow": None,                           # a day without a time isn't a time
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(when(spoken), expected)

    def test_clock_phrases(self):
        cases = {
            "at half past 9": "Wed 21:30",
            "at quarter past 10": "Wed 22:15",
            "at quarter to 11": "Wed 22:45",
            "at quarter to 2": "Thu 01:45",
            "at 10 past 9": "Wed 21:10",
            "at twenty to 11": "Wed 22:40",
            "at ten past nine pm": "Wed 21:10",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(when(spoken), expected)
        self.assertEqual(normalize_time_words("quarter to one"), "12:45")
        self.assertEqual(normalize_time_words("5 minutes past 3"), "3:05")
        self.assertEqual(normalize_time_words("add 5 to 10"), "add 5 to 10")

    def test_part_of_day(self):
        cases = {
            "at 3 in the afternoon": "Thu 15:00",
            "at 8 in the morning": "Thu 08:00",
            "at 9 in the evening": "Wed 21:00",
            "at 11 at night": "Wed 23:00",
            "at 12 at night": "Thu 00:00",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(when(spoken), expected)

    def test_weekdays(self):
        self.assertEqual(parse_when("wednesday at 9 pm", NOW)[0].date(), NOW.date())    # later today
        self.assertEqual(parse_when("next wednesday at 9 pm", NOW)[0].day, 28)
        self.assertEqual(parse_when("wednesday at 7 pm", NOW)[0].day, 28)                # already past
        self.assertEqual(when("next monday at 9"), "Mon 09:00")

    def test_durations_are_not_clock_phrases(self):
        self.assertEqual(when("in 10 minutes past the hour"), "Wed 20:25")


class CalcTest(unittest.TestCase):
    def test_maths(self):
        cases = {
            "what's 15% of 80": "12",
            "12 times 7": "84",
            "square root of 144": "12",
            "what's the square root of 2": "1.41421",
            "what is 5 plus 3 times 2": "11",
            "one hundred and five times 2": "210",      # not 100 + 5 * 2
            "a hundred plus five": "105",
            "two thousand plus 5": "2,005",
            "what's 1.5 million times 2": "3,000,000",
            "what's 20% off 50": "40",
            "15 percent tip on 80": "12",
            "what's 3 times negative 4": "-12",
            "1,000 plus 2,500": "3,500",
            "5 squared": "25",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                res = calculate(spoken)
                self.assertIsNotNone(res)
                self.assertEqual(res.card["result"], expected)

    def test_not_maths(self):
        for spoken in ("open spotify", "1 divided by 0", "what time is it"):
            with self.subTest(spoken=spoken):
                self.assertIsNone(calculate(spoken))

    def test_units(self):
        cases = {
            "convert 5 miles to km": "8.05 km",
            "70 fahrenheit in celsius": "21.1°C",
            "how many feet in a mile": "5,280 feet",
            "10 kg to pounds": "22.05 pounds",
            "100 km/h to mph": "62.14 mph",
            "how many seconds in a day": "86,400 seconds",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(convert(spoken).card["result"], expected)


if __name__ == "__main__":
    unittest.main()
