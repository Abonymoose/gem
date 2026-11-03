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
        replies._put_in_box.assert_called_once_with(
            "Dear Shah Sir,\n\nI hope you are doing well.\n\nCan we meet this week?\n\nThank you for your time and "
            "support.\n\nRegards,\nParshv Mehta", replace=False)          # paragraphs; just the body (no subject selected)
        self.assertTrue(res.endswith("Which day works for you?"))           # the question comes after the email
        self.assertIn("Subject: Meeting\n\nDear Shah Sir,", res.card["note"])

        self.selected.append("")                                             # nothing selected: an answer
        self.brain.complete.return_value = dict(self.brain.complete.return_value, question="",
                                                body="Dear Shah Sir,\n...Thursday...")
        replies.email_rewrite("thursday period 5")
        request = self.brain.complete.call_args[0][1]
        self.assertIn("Subject: Meeting", request)                          # the email Gem pasted, not the old draft
        self.assertIn("Request: thursday period 5", request)
        replies._put_in_box.assert_called_with("Dear Shah Sir,\n\n...Thursday...", replace=True)

    def test_selected_subject_comes_back_and_a_missing_name_is_asked(self):
        self.selected[0] = "Subject: URGENT!!! Meeting needed\n\nHi Sir,\nKindly let me know by Friday..."
        self.brain.complete.return_value = {"fine": False, "subject": "Meeting request", "question": "",
                                            "body": "Dear Sir,\nCan we meet this week?\nRegards,\nParshv Mehta"}
        res = replies.email_rewrite()
        replies._put_in_box.assert_called_once_with(
            "Subject: Meeting request\n\nDear Sir,\n\nCan we meet this week?\n\nRegards,\nParshv Mehta", replace=False)
        self.assertTrue(res.endswith("What's their name, for the greeting?"))

    def test_group_gets_dear_all_and_reply_all(self):
        self.selected[0] = ("To: Varsha Ma'am\nCC: Jayadev Sir, Meera Ma'am, Helen Ma'am\nSubject: Re: PTM Now Pilot "
                            "Update\n\nHello Ma'ams and Sir,\nJust wanted to quickly touch base!")
        self.brain.complete.return_value = {"fine": False, "subject": "Re: PTM Now Pilot Update", "question": "",
                                            "left_out": "who will share the student data",
                                            "body": "Dear Varsha Ma'am,\nCould you tell me?\nRegards,\nParshv Mehta"}
        res = replies.email_rewrite()
        replies._put_in_box.assert_called_once_with(
            "Subject: Re: PTM Now Pilot Update\n\nDear All,\n\nCan you tell me?\n\nRegards,\nParshv Mehta",
            replace=False)                              # subject after To/CC still counts; "Could you" is plain now
        self.assertIn("reply all", res)
        self.assertIn("I left out who will share the student data.", res)

    def test_ask_for_the_person_in_to_keeps_their_name(self):
        self.selected[0] = "To: Helen Ma'am\nCC: Jayadev Sir, Ekta Ma'am\nSubject: URGENT!!!\n\nHi Helen Ma'am,"
        self.brain.complete.return_value = {"fine": False, "subject": "Feedback form", "question": "",
                                            "to_only": True, "body": "Dear Helen Ma'am,\nCan you share it?"}
        res = replies.email_rewrite()
        self.assertIn("Dear Helen Ma'am,", replies._put_in_box.call_args[0][0])
        self.assertIn("reply all", res)                  # two CC'd: still reply all

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
