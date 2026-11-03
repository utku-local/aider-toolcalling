"""Pip arguments for Aider's optional features (Playwright scraping, the browser UI, interactive /help).
Upstream Aider installs each one as an `aider-chat[extra]`, which also installs upstream aider-chat into the
running environment and overwrites this package's patched aider/ files; here only the feature's own packages are named.
Measured 2026-11-03: accepting the Playwright offer replaced aider/io.py, main.py, args.py and coders/__init__.py.
"""

from typing import Final

PLAYWRIGHT_PACKAGES: Final[list[str]] = ["playwright"]
BROWSER_PACKAGES: Final[list[str]] = ["streamlit"]
# The CPU-only PyTorch index keeps /help from pulling a CUDA build of torch.
HELP_PACKAGES: Final[list[str]] = [
    "llama-index-embeddings-huggingface",
    "--extra-index-url",
    "https://download.pytorch.org/whl/cpu",
]
