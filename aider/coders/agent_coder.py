"""The agent chat mode: the model works through native tools, like a coding agent, instead of an edit format.
It enables the full tool set (read, search, edit, shell) and reports files changed by tools to Aider's normal
post-edit flow, so linting, auto-commits and tests behave as they do for any other edit.
Write approvals are grouped per request, so answering "All" approves the remaining edits of that request only.
"""

from typing import Any, Iterator

from aider.io import ConfirmGroup
from aider.native_toolcalling import NativeToolRegistry

from .agent_prompts import AgentPrompts
from .base_coder import Coder
from .native_tool_setup import build_native_tools


class AgentCoder(Coder):
    """Explore, edit and verify the project through tools."""

    edit_format = "agent"
    gpt_prompts = AgentPrompts()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["native_tools"] = True
        super().__init__(*args, **kwargs)

    def build_native_tools(self) -> NativeToolRegistry:
        return build_native_tools(self, include_actions=True)

    def send_message(self, inp: str) -> Iterator[str]:
        self.native_write_group = ConfirmGroup()
        return super().send_message(inp)

    def check_for_file_mentions(self, content: str) -> None:
        """The agent reads files through tools, so mentions never prompt to add files."""
        return None

    def apply_updates(self) -> set[str]:
        """Files changed by tools during this reply, relative to the root."""
        edited = {self.get_rel_fname(path) for path in self.native_pending_edits}
        self.native_pending_edits.clear()
        return edited
