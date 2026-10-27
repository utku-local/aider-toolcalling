"""Entry point of the aider-agent command: Aider with this package's patches, started in agent mode.
It prepends --agent to the command line, so any later --chat-mode or --edit-format still overrides the mode.
Installed with the package, it needs no PYTHONPATH and does not touch an existing aider command.
"""

import sys
from typing import Optional

from aider.main import main as aider_main

AGENT_FLAG = "--agent"


def main(argv: Optional[list[str]] = None) -> Optional[int]:
    args = sys.argv[1:] if argv is None else argv
    return aider_main([AGENT_FLAG, *args])


if __name__ == "__main__":
    sys.exit(main())
