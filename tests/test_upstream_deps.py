"""Tests for syncing dependencies with an upstream aider-chat release.
Requirements tied to extras are skipped, and the rewritten pyproject.toml must stay valid TOML even when markers
contain double quotes; a pyproject without a dependencies array is an error.
The real pyproject.toml must be reproducible from its own dependency list.
"""

import tomllib
import unittest
from pathlib import Path

from maintenance.upstream_deps import PyprojectError, replace_dependencies, runtime_requirements

METADATA = """Name: aider-chat
Version: 9.9.9
Requires-Dist: litellm==1.0
Requires-Dist: tree-sitter==0.23.2; python_version < "3.10"
Requires-Dist: pytest==8; extra == "dev"
"""
PYPROJECT = '[project]\nname = "x"\ndependencies = [\n    "old==1",\n]\n\n[project.scripts]\na = "b:c"\n'


class UpstreamDepsTest(unittest.TestCase):
    def test_runtime_requirements_skip_extras(self) -> None:
        self.assertEqual(runtime_requirements(METADATA),
                         ["litellm==1.0", 'tree-sitter==0.23.2; python_version < "3.10"'])

    def test_replace_dependencies_keeps_valid_toml(self) -> None:
        updated = replace_dependencies(PYPROJECT, runtime_requirements(METADATA))
        data = tomllib.loads(updated)
        self.assertEqual(data["project"]["dependencies"][1], 'tree-sitter==0.23.2; python_version < "3.10"')
        self.assertEqual(data["project"]["scripts"], {"a": "b:c"})
        with self.assertRaises(PyprojectError):
            replace_dependencies("[project]\n", [])

    def test_real_pyproject_round_trips(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath("pyproject.toml").read_text()
        dependencies = tomllib.loads(text)["project"]["dependencies"]
        self.assertEqual(replace_dependencies(text, dependencies), text)


if __name__ == "__main__":
    unittest.main()
