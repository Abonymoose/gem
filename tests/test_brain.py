"""Reading the AI planner's replies, which don't always come back as clean JSON."""
import unittest

from . import svc  # noqa: F401  (sets up the test environment)
from gem.brain import _clean_plan, _parse_json


class ParseTest(unittest.TestCase):
    def test_messy_replies(self):
        plan = {"addressed": True, "actions": [{"name": "set_timer", "args": {"minutes": 5}}], "reply": ""}
        for raw in ('{"addressed": true, "actions": [{"name": "set_timer", "args": {"minutes": 5}}], "reply": ""}',
                    '```json\n{"addressed": true, "actions": [{"name": "set_timer", "args": {"minutes": 5}}], '
                    '"reply": ""}\n```',
                    '<think>The user wants {a timer}.</think>{"addressed": true, "actions": [{"name": "set_timer", '
                    '"args": {"minutes": 5}}], "reply": ""}',
                    'Sure! {"addressed": true, "actions": [{"name": "set_timer", "args": {"minutes": 5}}], '
                    '"reply": ""} Hope that helps {:}'):
            with self.subTest(raw=raw[:40]):
                self.assertEqual(_parse_json(raw), plan)
        self.assertIsNone(_parse_json("no json here"))
        self.assertIsNone(_parse_json(""))

    def test_clean_plan(self):
        p = _clean_plan({"addressed": "false", "actions": [{"name": "set_timer", "args": {}}], "reply": "Hi"}, "open")
        self.assertEqual((p["addressed"], p["actions"], p["reply"]), (False, [], ""))
        p = _clean_plan({"addressed": False, "reply": "Hi"}, "ptt")          # push-to-talk is always for Gem
        self.assertTrue(p["addressed"])
        p = _clean_plan({"actions": [{"name": "no_such_action"}, {"name": "set_timer", "args": "bad"}],
                         "reply": "Done."}, "ptt")
        self.assertEqual(p["actions"], [{"name": "set_timer", "args": {}}])
        self.assertEqual(p["reply"], "")                                      # actions confirm themselves


if __name__ == "__main__":
    unittest.main()
