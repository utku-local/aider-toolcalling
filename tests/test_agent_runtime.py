"""Tests for the agent runtime: sandbox, background commands, fetch_url, session save and resume, aider-agent.
The sandbox test runs real commands under sandbox-exec and is skipped where it is missing; it checks that writes
outside the project fail while writes inside succeed. Fetch tests never touch the network.
Session tests round-trip a real AgentCoder through the session file.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_agent_coder import tool_call
from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion

from aider import agent_main
from aider.coders import Coder
from aider.coders.native_agent_config import parse_config
from aider.coders.native_session import PREVIOUS_FILE_NAME, SESSION_FILE_NAME, resume_session
from aider.io import InputOutput
from aider.models import Model
from aider.native_sandbox import sandbox_available, sandbox_profile, sandboxed_argv, shell_argv
from aider.native_tool_context import ToolContext, ToolPermission
from aider.native_tools_background import BackgroundError, ProcessManager
from aider.native_tool_context import DENIED_ACTION
from aider.native_tools_fetch import FetchError, fetch_url, html_to_text
from aider.native_tools_shell import run_command

POLL_SECONDS = 0.1
POLL_ATTEMPTS = 50


def context(root: Path, approve: bool = True, sandboxed: bool = False) -> ToolContext:
    return ToolContext(
        root=root, list_files=list, find_tags=lambda a, r: [], approve=lambda p, t, d: approve,
        on_edit=lambda p: None, dry_run=False,
        wrap_command=(lambda c: sandboxed_argv(root, c)) if sandboxed else shell_argv,
    )


class SandboxTest(unittest.TestCase):
    def test_profile_limits_writes_and_network(self) -> None:
        profile = sandbox_profile(Path("/work/my \"proj\""))
        self.assertIn("(deny network*)", profile)
        self.assertIn('(subpath "/work/my \\"proj\\"")', profile)

    @unittest.skipUnless(sandbox_available(), "sandbox-exec is not available")
    def test_commands_cannot_write_outside_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory(dir=Path.home()) as outside:
            root = Path(tmp).resolve()
            ctx = context(root, sandboxed=True)
            self.assertTrue(run_command(ctx, "echo ok > inside.txt").startswith("Exit code: 0"))
            self.assertTrue((root / "inside.txt").exists())
            result = run_command(ctx, f"echo bad > {outside}/escape.txt")
            self.assertFalse(result.startswith("Exit code: 0"))
            self.assertFalse(Path(outside, "escape.txt").exists())

    def test_config_sandbox_flag(self) -> None:
        self.assertTrue(parse_config({"sandbox": True}).sandbox)
        self.assertFalse(parse_config({}).sandbox)


class BackgroundTest(unittest.TestCase):
    def test_start_read_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ProcessManager()
            process_id = manager.start(shell_argv("echo started; sleep 30"), Path(tmp), "server")
            for _ in range(POLL_ATTEMPTS):
                output = manager.read(process_id)
                if "started" in output:
                    break
                time.sleep(POLL_SECONDS)
            self.assertIn("running", output)
            self.assertIn("started", output)
            self.assertNotIn("started", manager.read(process_id).split("\n", 1)[1])
            self.assertIn("exited", manager.stop(process_id))
            with self.assertRaises(BackgroundError):
                manager.read("bg99")
            manager.stop_all()


class FetchTest(unittest.TestCase):
    def test_html_to_text_drops_scripts(self) -> None:
        html = "<html><head><style>x{}</style><script>alert(1)</script></head><body><h1>Title</h1><p>Body</p>"
        self.assertEqual(html_to_text(html), "Title\nBody")

    def test_scheme_check_and_denial_happen_before_any_download(self) -> None:
        asked = []
        ctx = ToolContext(Path("/"), list, lambda a, r: [], lambda p, t, d: asked.append(p) or False,
                          lambda p: None, False)
        with self.assertRaises(FetchError):
            fetch_url(ctx, "file:///etc/passwd")
        with patch("aider.native_tools_fetch.download") as download:
            self.assertEqual(fetch_url(ctx, "https://example.com"), DENIED_ACTION)
            download.assert_not_called()
        self.assertEqual(asked, [ToolPermission.NETWORK])


class SessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("def add(a, b):\n    return a - b\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def make_coder(self) -> Coder:
        return Coder.create(main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
                            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False)

    def test_session_round_trip(self) -> None:
        coder = self.make_coder()
        plan = {"items": [{"content": "Fix add", "status": "in_progress"}]}
        read = tool_call("r1", "read_file", {"path": "calc.py"}) + tool_call("t1", "todo_write", plan)
        scripted = ScriptedModel([make_completion(tool_calls=read), make_completion(FINAL_TEXT)])
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Plan the fix.")
        saved = json.loads(Path(SESSION_FILE_NAME).read_text())
        self.assertEqual([r["call_id"] for r in saved["ledger"]], ["r1", "t1"])

        resumed = self.make_coder()
        self.assertTrue(resume_session(resumed))
        self.assertEqual(len(resumed.native_ledger.records), 2)
        self.assertEqual(resumed.native_ledger.request, 1)
        self.assertEqual(resumed.native_todos.render(), "[~] Fix add")
        self.assertTrue(any(m.get("role") == "tool" for m in resumed.done_messages))

    def test_resume_without_a_session_reports_an_error(self) -> None:
        self.assertFalse(resume_session(self.make_coder()))

    def run_one_request(self, coder: Coder, call_id: str) -> None:
        read = tool_call(call_id, "read_file", {"path": "calc.py"})
        scripted = ScriptedModel([make_completion(tool_calls=read), make_completion(FINAL_TEXT)])
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Look at calc.py.")

    def ledger_ids(self, name: str) -> list:
        return [r["call_id"] for r in json.loads(Path(name).read_text())["ledger"]]

    def test_a_new_session_keeps_the_previous_one(self) -> None:
        self.run_one_request(self.make_coder(), "old")
        fresh = self.make_coder()
        self.run_one_request(fresh, "new1")
        self.run_one_request(fresh, "new2")
        self.assertEqual(self.ledger_ids(PREVIOUS_FILE_NAME), ["old"])
        self.assertEqual(self.ledger_ids(SESSION_FILE_NAME), ["new1", "new2"])

    def test_a_resumed_session_saves_in_place(self) -> None:
        self.run_one_request(self.make_coder(), "old")
        resumed = self.make_coder()
        self.assertTrue(resume_session(resumed))
        self.run_one_request(resumed, "more")
        self.assertFalse(Path(PREVIOUS_FILE_NAME).exists())
        self.assertEqual(self.ledger_ids(SESSION_FILE_NAME), ["old", "more"])


class AgentMainTest(unittest.TestCase):
    def test_agent_flag_is_prepended(self) -> None:
        with patch("aider.agent_main.aider_main", return_value=0) as main, \
                patch("aider.agent_main.agent_flags", return_value=["--agent"]):
            agent_main.main(["--model", "x", "--chat-mode", "ask"])
        main.assert_called_once_with(["--agent", "--model", "x", "--chat-mode", "ask"])

    def test_agent_settings_file_is_used_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp, ".aider.agent.model.settings.yml")
            self.assertEqual(agent_main.agent_flags(settings), ["--agent"])
            settings.write_text("- name: x\n")
            self.assertEqual(agent_main.agent_flags(settings), ["--agent", "--model-settings-file", str(settings)])


if __name__ == "__main__":
    unittest.main()
