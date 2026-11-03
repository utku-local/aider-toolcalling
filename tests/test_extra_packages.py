"""Tests that Aider's optional-feature installs never install upstream aider-chat over this package.
Accepting the Playwright offer once ran pip install aider-chat[playwright], which overwrote patched aider/ files.
The checks scan the package source for that install form and confirm each feature names only its own packages.
"""

import unittest
from pathlib import Path

from aider import extra_packages
from aider.extra_packages import BROWSER_PACKAGES, HELP_PACKAGES, PLAYWRIGHT_PACKAGES

PACKAGE_DIR = Path(extra_packages.__file__).parent
UPSTREAM_INSTALL = '"aider-chat['
UPSTREAM_NAME = "aider-chat"
SOURCE_GLOB = "*.py"


class ExtraPackagesTest(unittest.TestCase):
    def test_no_source_file_installs_upstream_aider_chat(self) -> None:
        offenders = [
            str(path.relative_to(PACKAGE_DIR))
            for path in PACKAGE_DIR.rglob(SOURCE_GLOB)
            if UPSTREAM_INSTALL in path.read_text(encoding="utf-8", errors="replace")
        ]
        self.assertEqual(offenders, [])

    def test_each_feature_names_its_own_packages(self) -> None:
        self.assertEqual(PLAYWRIGHT_PACKAGES, ["playwright"])
        self.assertEqual(BROWSER_PACKAGES, ["streamlit"])
        self.assertIn("llama-index-embeddings-huggingface", HELP_PACKAGES)
        for packages in (PLAYWRIGHT_PACKAGES, BROWSER_PACKAGES, HELP_PACKAGES):
            self.assertFalse(any(arg.startswith(UPSTREAM_NAME) for arg in packages))


if __name__ == "__main__":
    unittest.main()
