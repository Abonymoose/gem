"""The email rewriter: the commands, pasting over the selection, asking after writing, and the answer to that
question rewriting the same email. The AI and the keyboard are faked."""
import unittest
from unittest import mock

from . import svc  # noqa: F401  (sets up the test environment)
from .test_router import route
from gem.runtime import svc as runtime_svc
from gem.skills import replies


class RoutesTest(unittest.TestCase):
    def test_commands(self):
        m = route("rewrite the email I have selected")
        self.assertEqual((m.action, m.args), ("email_rewrite", {"instruction": ""}))
        self.assertFalse(m.safe)
        m = route("rewrite the email i have selected and ask for a meeting on thursday")
        self.assertEqual(m.args, {"instruction": "ask for a meeting on thursday"})
        self.assertEqual(route("rewrite this email").action, "email_rewrite")
        self.assertEqual(route("rewrite this").action, "text_tool")         # other text still gets the plain rewrite


class RewriteTest(unittest.TestCase):
    def setUp(self):
        replies._email.update(text="", at=0.0, hwnd=0)
        self.brain = mock.Mock()
        self.selected = ["dear sir i wanted to reach out, can we meet. thanks parshv"]
        patches = [mock.patch.object(runtime_svc, "brain", self.brain),
                   mock.patch.object(replies, "copy_selection", side_effect=lambda: self.selected.pop(0)),
                   mock.patch.object(replies, "foreground_window", return_value=7),
                   mock.patch.object(replies, "_put_in_box")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_writes_first_then_asks_and_the_answer_rewrites_it(self):
        self.brain.complete.return_value = {
            "fine": False, "subject": "Meeting", "question": "Which day works for you?",
            "body": "Dear Shah Sir,\nI hope you are doing well.\nCan we meet this week?\nThank you for your time "
                    "and support.\nRegards,\nParshv Mehta"}
        res = replies.email_rewrite()
        replies._put_in_box.assert_called_once_with(self.brain.complete.return_value["body"], replace=False)
        self.assertTrue(res.endswith("Which day works for you?"))           # the question comes after the email
        self.assertIn("Subject: Meeting\n\nDear Shah Sir,", res.card["note"])

        self.selected.append("")                                             # nothing selected: an answer
        self.brain.complete.return_value = dict(self.brain.complete.return_value, question="",
                                                body="Dear Shah Sir,\n...Thursday...")
        replies.email_rewrite("thursday period 5")
        request = self.brain.complete.call_args[0][1]
        self.assertIn("Subject: Meeting", request)                          # the email Gem pasted, not the old draft
        self.assertIn("Request: thursday period 5", request)
        replies._put_in_box.assert_called_with("Dear Shah Sir,\n...Thursday...", replace=True)

    def test_fine_draft_is_left_alone(self):
        self.brain.complete.return_value = {"fine": True, "subject": "", "body": "", "question": ""}
        self.assertIn("already follows your rules", replies.email_rewrite())
        replies._put_in_box.assert_not_called()

    def test_nothing_selected(self):
        self.selected[0] = ""
        with self.assertRaisesRegex(replies.ActionError, "Select the email first"):
            replies.email_rewrite()
        self.brain.complete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
