"""Tests for plan approval in todo_write, the ask_user tool and the plan_approval setting.
They check that only the first plan of a request is shown, that a rejected plan is cleared with the user's note,
that unattended runs approve plans and get no answers, and that numbered choices map back to the choice.
The io adapters are exercised with a stub io, so no terminal is needed.
"""

import unittest
from types import SimpleNamespace

from aider.coders.native_agent_config import AgentConfigError, parse_config
from aider.coders.native_user_io import answer_question, confirm_plan
from aider.native_todo import PLAN_APPROVED, TodoList, todo_write
from aider.native_tools_ask import ASK_PARAMETERS, MAX_CHOICES, NO_USER, AskError, ask_user, resolve_choice

PLAN = [{"content": "Read the code", "status": "in_progress"}, {"content": "Run the tests"}]


class PlanApprovalTest(unittest.TestCase):
    def test_first_plan_is_shown_once_per_request(self) -> None:
        todos, shown = TodoList(), []

        def confirm(plan: str) -> bool:
            shown.append(plan)
            return True

        self.assertTrue(todo_write(todos, PLAN, confirm).startswith(PLAN_APPROVED))
        todo_write(todos, [{"content": "Read the code", "status": "done"}], confirm)
        self.assertEqual(len(shown), 1)
        todos.approved = False
        todo_write(todos, PLAN, confirm)
        self.assertEqual(len(shown), 2)

    def test_rejected_plan_is_cleared_with_the_note(self) -> None:
        todos = TodoList()
        result = todo_write(todos, PLAN, lambda plan: False, lambda question: "add a test first")
        self.assertIn("add a test first", result)
        self.assertEqual(todos.items, ())
        self.assertFalse(todos.approved)

    def test_without_confirm_nothing_is_asked(self) -> None:
        self.assertNotIn(PLAN_APPROVED, todo_write(TodoList(), PLAN))


class AskUserTest(unittest.TestCase):
    def test_numbered_and_exact_choices_map_back(self) -> None:
        choices = ["keep it", "rewrite it"]
        self.assertEqual(resolve_choice("2", choices), "rewrite it")
        self.assertEqual(resolve_choice("Keep It", choices), "keep it")
        self.assertEqual(resolve_choice("something else", choices), "something else")

    def test_reply_and_no_user(self) -> None:
        self.assertEqual(ask_user(lambda q, c: "1", "Which?", ["a", "b"]), "The user answered: a")
        self.assertEqual(ask_user(lambda q, c: None, "Which?"), NO_USER)

    def test_bad_questions_are_refused(self) -> None:
        with self.assertRaises(AskError):
            ask_user(lambda q, c: "x", "  ")
        with self.assertRaises(AskError):
            ask_user(lambda q, c: "x", "Which?", ["ok", ""])

    def test_refusal_names_the_problem(self) -> None:
        cases = [
            (["o"] * (MAX_CHOICES + 1), f"got {MAX_CHOICES + 1} options, at most {MAX_CHOICES}"),
            (["ok", {"label": "b"}], "option 2 is a dict; each option must be a plain string"),
            (["ok", " "], "option 2 is empty"),
        ]
        for options, message in cases:
            with self.subTest(options=options), self.assertRaisesRegex(AskError, message):
                ask_user(lambda q, c: "x", "Which?", options)

    def test_schema_declares_option_shape(self) -> None:
        options = ASK_PARAMETERS["properties"]["options"]
        self.assertEqual(options["items"], {"type": "string"})
        self.assertEqual(options["maxItems"], MAX_CHOICES)


class UserIoTest(unittest.TestCase):
    def make_coder(self, yes: object, reply: str = "", approve: bool = True) -> SimpleNamespace:
        printed: list[str] = []
        io = SimpleNamespace(yes=yes, tool_output=printed.append,
                             prompt_ask=lambda question, default="": reply,
                             confirm_ask=lambda title, subject=None, allow_never=None: approve)
        return SimpleNamespace(io=io, printed=printed)

    def test_unattended_runs_approve_and_get_no_answer(self) -> None:
        coder = self.make_coder(yes=True, approve=False)
        self.assertTrue(confirm_plan(coder, "plan"))
        self.assertIsNone(answer_question(coder, "Which?", ["a"]))

    def test_interactive_run_shows_choices_and_reads_the_reply(self) -> None:
        coder = self.make_coder(yes=None, reply=" 2 ", approve=False)
        self.assertFalse(confirm_plan(coder, "plan"))
        self.assertEqual(answer_question(coder, "Which?", ["a", "b"]), "2")
        self.assertEqual(coder.printed, ["  1. a", "  2. b"])


class PlanApprovalConfigTest(unittest.TestCase):
    def test_default_on_and_can_be_turned_off(self) -> None:
        self.assertTrue(parse_config({}).plan_approval)
        self.assertFalse(parse_config({"plan_approval": False}).plan_approval)
        with self.assertRaises(AgentConfigError):
            parse_config({"plan_approval": "no"})
