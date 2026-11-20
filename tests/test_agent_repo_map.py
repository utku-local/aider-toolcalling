"""Tests that agent mode keeps one repo map across tool rounds, so a server's prompt cache stays valid.
A small git project is mapped twice with different names mentioned in the conversation in between.
An explicit --map-refresh choice of the user must be left alone.
"""

import os
import subprocess
import tempfile
import unittest

from test_coder_native_tools import MODEL_NAME

from aider.coders import Coder
from aider.coders.agent_coder import MAP_REFRESH_FILES
from aider.io import InputOutput
from aider.models import Model
from aider.repo import GitRepo

# More modules than fit in the map, so which ones are shown depends on how they are ranked.
MODULES = 60
MAP_TOKENS = 256
GIT_IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com")


class AgentRepoMapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        for index in range(MODULES):
            with open(f"mod{index}.py", "w") as handle:
                handle.write(f"def helper{index}(value):\n    return value + {index}\n\n\n"
                             f"def user{index}(value):\n    return helper{(index + 1) % MODULES}(value)\n")
        subprocess.run(["git", "init", "-q"], check=True)
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", *GIT_IDENTITY, "commit", "-qm", "init"], check=True)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def make_coder(self, **kwargs: str) -> Coder:
        io = InputOutput(yes=True, pretty=False)
        return Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=io, fnames=[], repo=GitRepo(io, [], None),
            map_tokens=MAP_TOKENS, auto_lint=False, stream=False, **kwargs,
        )

    def test_the_map_does_not_change_with_the_names_in_the_conversation(self) -> None:
        coder = self.make_coder()
        self.assertEqual(coder.repo_map.refresh, MAP_REFRESH_FILES)
        coder.cur_messages = [{"role": "user", "content": "look at helper3 in mod3.py"}]
        first = coder.get_repo_map()
        coder.cur_messages = [{"role": "user", "content": "now user9 and helper10 in mod9.py and mod10.py"}]
        self.assertTrue(first)
        self.assertEqual(coder.get_repo_map(), first)

    def test_an_explicit_refresh_choice_is_kept_and_does_follow_the_conversation(self) -> None:
        coder = self.make_coder(map_refresh="always")
        self.assertEqual(coder.repo_map.refresh, "always")
        coder.cur_messages = [{"role": "user", "content": "look at helper3 in mod3.py"}]
        first = coder.get_repo_map()
        coder.cur_messages = [{"role": "user", "content": "now user9 and helper10 in mod9.py and mod10.py"}]
        self.assertNotEqual(coder.get_repo_map(), first)


if __name__ == "__main__":
    unittest.main()
