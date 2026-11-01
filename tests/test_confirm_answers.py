"""Tests for reading replies to confirmation prompts and handing typed messages to the model.
A prompt accepts only the answers it shows, asks again for anything else, and queues a reply of several words as a
note; the agent loop turns queued notes into one user message, and a declined command asks what to do instead.
The prompt is driven through Python's input(), so no terminal is needed.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aider.coders.native_user_io import USER_NOTE_HEADING, ask_after_decline, take_user_notes
from aider.confirm_answers import ALL, DONT, NO, SKIP, YES, ReplyKind, classify_reply, offered_answers
from aider.io import ConfirmGroup, InputOutput

TYPED_MESSAGE = "i did not decline this, please accept it and carry on"


def plain_io() -> InputOutput:
    return InputOutput(pretty=False, fancy_input=False)


class OfferedAnswersTest(unittest.TestCase):
    def test_bare_prompt_offers_yes_and_no_only(self) -> None:
        self.assertEqual(offered_answers(False, True, False), [YES, NO])

    def test_group_and_never_add_their_answers(self) -> None:
        self.assertEqual(offered_answers(True, False, True), [YES, NO, ALL, SKIP, DONT])
        self.assertEqual(offered_answers(True, True, False), [YES, NO, SKIP])


class ClassifyReplyTest(unittest.TestCase):
    def test_prefixes_of_offered_answers(self) -> None:
        self.assertEqual(classify_reply("Y", [YES, NO]), (ReplyKind.ANSWER, YES))
        self.assertEqual(classify_reply(" no ", [YES, NO]), (ReplyKind.ANSWER, NO))
        self.assertEqual(classify_reply("a", [YES, NO, ALL]), (ReplyKind.ANSWER, ALL))

    def test_answers_not_offered_are_invalid(self) -> None:
        for reply in ("a", "all", "s", "6"):
            with self.subTest(reply=reply):
                self.assertEqual(classify_reply(reply, [YES, NO]), (ReplyKind.INVALID, None))

    def test_several_words_are_a_note(self) -> None:
        self.assertEqual(classify_reply(TYPED_MESSAGE, [YES, NO]), (ReplyKind.NOTE, TYPED_MESSAGE))


class ConfirmAskTest(unittest.TestCase):
    def ask(self, replies: list[str], **kwargs: object) -> tuple[bool, InputOutput]:
        io = plain_io()
        with patch("builtins.input", side_effect=replies):
            return io.confirm_ask("Run this command?", **kwargs), io

    def test_a_at_a_yes_no_prompt_is_asked_again_not_declined(self) -> None:
        approved, _ = self.ask(["a", "y"], explicit_yes_required=True)
        self.assertTrue(approved)

    def test_a_typed_message_is_queued_and_the_question_repeated(self) -> None:
        approved, io = self.ask([TYPED_MESSAGE, "n"], explicit_yes_required=True)
        self.assertFalse(approved)
        self.assertEqual(io.pending_user_notes, [TYPED_MESSAGE])

    def test_all_still_works_for_grouped_prompts(self) -> None:
        group = ConfirmGroup(["a.py", "b.py"])
        approved, _ = self.ask(["a"], group=group)
        self.assertTrue(approved)
        self.assertEqual(group.preference, ALL)


class UserNotesTest(unittest.TestCase):
    def test_notes_become_one_user_message_once(self) -> None:
        coder = SimpleNamespace(io=SimpleNamespace(pending_user_notes=["first", "second"]))
        self.assertEqual(take_user_notes(coder), {"role": "user", "content": USER_NOTE_HEADING + "first\nsecond"})
        self.assertIsNone(take_user_notes(coder))

    def test_decline_follow_up_is_queued_when_someone_can_answer(self) -> None:
        io = plain_io()
        with patch("builtins.input", return_value="use the venv python"):
            ask_after_decline(SimpleNamespace(io=io))
        self.assertEqual(io.pending_user_notes, ["use the venv python"])

    def test_unattended_runs_are_not_asked(self) -> None:
        io = InputOutput(pretty=False, fancy_input=False, yes=True)
        with patch("builtins.input") as typed:
            ask_after_decline(SimpleNamespace(io=io))
        typed.assert_not_called()
        self.assertEqual(io.pending_user_notes, [])


if __name__ == "__main__":
    unittest.main()
