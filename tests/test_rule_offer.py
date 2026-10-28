"""Tests for "always allow": which rule a command earns, how it is saved, and when the question is asked.
Only plain, risk-free commands earn a rule, and programs with subcommands get a rule for that subcommand only.
The offer is skipped when a rule already allows the command, and a declined offer changes nothing.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from aider.coders.native_agent_config import AgentConfig, add_allow_rule, load_agent_config
from aider.coders.native_rule_offer import offer_allow_rule
from aider.native_command_policy import CommandRule, PolicyAction, decide, rule_for_command

ROOT = Path("/work/project")


class RuleForCommandTest(unittest.TestCase):
    def test_rules(self) -> None:
        self.assertEqual(rule_for_command("pytest -q tests", ROOT, False), CommandRule("pytest"))
        self.assertEqual(rule_for_command("python -m unittest tests/test_a.py", ROOT, True),
                         CommandRule("unittest", (), True))
        self.assertEqual(rule_for_command("git status --short", ROOT, False), CommandRule("git", ("status",)))
        for command in ("pytest | tee x", "git push origin main", "curl https://x", "rm a.txt", "git --version",
                        "sudo ls", "pytest ../other"):
            with self.subTest(command=command):
                self.assertIsNone(rule_for_command(command, ROOT, False))


class AddRuleTest(unittest.TestCase):
    def test_add_allow_rule_creates_and_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = add_allow_rule(tmp, AgentConfig(), CommandRule("pytest", (), True))
            config = add_allow_rule(tmp, config, CommandRule("git", ("status",)))
            saved = json.loads(Path(tmp, ".aider-agent.json").read_text())
            self.assertEqual(saved["commands"]["allow"], [
                {"program": "pytest", "trust_unsandboxed": True},
                {"program": "git", "subcommands": ["status"]},
            ])
            self.assertEqual(load_agent_config(tmp, None).rules, config.rules)


class OfferTest(unittest.TestCase):
    def coder(self, root: str, answer: bool) -> SimpleNamespace:
        asked: list = []
        io = SimpleNamespace(confirm_ask=lambda q, **kw: asked.append((q, kw)) or answer,
                             tool_output=lambda *a: None)
        return SimpleNamespace(root=root, io=io, native_sandboxed=False, native_agent_config=AgentConfig(),
                               asked=asked)

    def test_confirmed_offer_adds_a_trusted_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            coder = self.coder(tmp, True)
            offer_allow_rule(coder, "pytest -q")
            question, kwargs = coder.asked[0]
            self.assertIn("also outside the sandbox", question)
            self.assertTrue(kwargs["explicit_yes_required"])
            root = Path(tmp).resolve()
            self.assertIs(decide("pytest -x", root, coder.native_agent_config.rules, False).action,
                          PolicyAction.ALLOW)
            offer_allow_rule(coder, "pytest -x")
            self.assertEqual(len(coder.asked), 1)

    def test_declined_or_risky_commands_change_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            coder = self.coder(tmp, False)
            offer_allow_rule(coder, "pytest")
            offer_allow_rule(coder, "curl https://example.com")
            self.assertEqual(len(coder.asked), 1)
            self.assertFalse(Path(tmp, ".aider-agent.json").exists())


if __name__ == "__main__":
    unittest.main()
