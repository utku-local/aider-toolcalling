"""Entry point of the aider-agent command: Aider with this package's patches, started in agent mode.
It prepends --agent to the command line, so any later --chat-mode or --edit-format still overrides the mode, and
loads ~/.aider.agent.model.settings.yml when present, so the agent can use its own model server (for example an
mlx_lm server with prefix caching) while plain aider keeps the usual settings.
"""

import sys
from pathlib import Path
from typing import Optional

from aider.main import main as aider_main

AGENT_FLAG = "--agent"
SETTINGS_FLAG = "--model-settings-file"
AGENT_SETTINGS_NAME = ".aider.agent.model.settings.yml"


def agent_flags(settings_file: Path) -> list[str]:
    """--agent, plus the agent-only model settings file when it exists."""
    if settings_file.is_file():
        return [AGENT_FLAG, SETTINGS_FLAG, str(settings_file)]
    return [AGENT_FLAG]


def main(argv: Optional[list[str]] = None) -> Optional[int]:
    args = sys.argv[1:] if argv is None else argv
    return aider_main([*agent_flags(Path.home() / AGENT_SETTINGS_NAME), *args])


if __name__ == "__main__":
    sys.exit(main())
