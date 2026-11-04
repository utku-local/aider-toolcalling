"""Loads the agent's project configuration from .aider-agent.json in the project root.
It reads command allow and deny rules for the command policy and whether commands run in the macOS sandbox;
a missing file means no rules and no sandbox, and a malformed file is reported once and ignored the same way.
Instruction files such as AGENTS.md are found here too, so the AgentCoder can add them read-only to the chat.
"""

import dataclasses
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from aider.native_hooks import HookRule
from aider.native_mcp_oauth import OAuthSettings
from aider.native_web_policy import WebPolicy
from aider.native_command_policy import CommandRule, CommandRules

CONFIG_FILE_NAME = ".aider-agent.json"
# The agent's own notes from earlier sessions (native_memory_skills.MEMORY_FILE) are read like instructions.
INSTRUCTION_FILE_NAMES = ("AGENTS.md", "CLAUDE.md", ".aider-agent/memory.md")
MAX_INSTRUCTION_BYTES = 50_000
CONFIG_ENCODING = "utf-8"
# A search service for every project that sets none, e.g. http://127.0.0.1:8888/search?q={query}&format=json
DEFAULT_SEARCH_URL = os.getenv("AIDER_AGENT_SEARCH_URL", "")
QUERY_FIELD = "{query}"


@dataclass(frozen=True)
class MCPServerConfig:
    """A stdio MCP server (`command`) or an HTTP one (`url`, with `headers` and optional `oauth` sign-in); `trusted`
    lets its tools run without asking. Defaults: no extra environment, no URL, no headers, not trusted, no OAuth."""

    name: str
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()
    trusted: bool = False
    url: str = ""
    headers: tuple[tuple[str, str], ...] = ()
    oauth: Optional[OAuthSettings] = None


@dataclass(frozen=True)
class AgentConfig:
    """Project settings; defaults: no command rules, no sandbox, no MCP servers, plans shown for approval."""

    rules: CommandRules = CommandRules()
    sandbox: bool = False
    mcp_servers: tuple[MCPServerConfig, ...] = ()
    plan_approval: bool = True
    web: WebPolicy = WebPolicy()
    before_hooks: tuple[HookRule, ...] = ()
    after_hooks: tuple[HookRule, ...] = ()
    thinking: Optional[bool] = None


class AgentConfigError(ValueError):
    """Raised when .aider-agent.json does not have the expected shape."""


def parse_rule(raw: Any) -> CommandRule:
    if not isinstance(raw, dict) or not isinstance(raw.get("program"), str):
        raise AgentConfigError('each rule needs a "program" string')
    subcommands = raw.get("subcommands", [])
    if not isinstance(subcommands, list) or not all(isinstance(s, str) for s in subcommands):
        raise AgentConfigError('"subcommands" must be a list of strings')
    return CommandRule(raw["program"], tuple(subcommands), bool(raw.get("trust_unsandboxed", False)))


def parse_http_mcp_server(name: str, raw: dict) -> MCPServerConfig:
    headers = raw.get("headers", {})
    if not isinstance(headers, dict) or not all(isinstance(v, str) for v in headers.values()):
        raise AgentConfigError(f'MCP server {name!r}: "headers" must map names to strings')
    if not raw["url"].startswith(("http://", "https://")):
        raise AgentConfigError(f'MCP server {name!r}: "url" must be an http or https URL')
    return MCPServerConfig(name, (), (), bool(raw.get("trusted")), raw["url"], tuple(sorted(headers.items())),
                           parse_oauth(name, raw.get("oauth", False)))


def parse_oauth(name: str, raw: Any) -> Optional[OAuthSettings]:
    """"oauth": true signs in with dynamic client registration; an object may set client_id, scope, callback_port."""
    if raw is False:
        return None
    if raw is True:
        return OAuthSettings()
    fields = {"client_id": str, "scope": str, "callback_port": int}
    if not isinstance(raw, dict) or any(k not in fields or not isinstance(v, fields[k]) for k, v in raw.items()):
        raise AgentConfigError(f'MCP server {name!r}: "oauth" must be true or an object with client_id (string), '
                               'scope (string) and callback_port (integer)')
    return OAuthSettings(**raw)


def parse_mcp_server(name: str, raw: Any) -> MCPServerConfig:
    if isinstance(raw, dict) and isinstance(raw.get("url"), str):
        return parse_http_mcp_server(name, raw)
    if not isinstance(raw, dict) or not isinstance(raw.get("command"), str):
        raise AgentConfigError(f'MCP server {name!r} needs a "command" or "url" string')
    args = raw.get("args", [])
    env = raw.get("env", {})
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise AgentConfigError(f'MCP server {name!r}: "args" must be a list of strings')
    if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
        raise AgentConfigError(f'MCP server {name!r}: "env" must map names to strings')
    return MCPServerConfig(name, (raw["command"], *args), tuple(sorted(env.items())), bool(raw.get("trusted")))


def parse_web(raw: Any) -> WebPolicy:
    """The "network" section: {"allow_domains": [...], "search": true|false, "search_url": "...{query}..."}."""
    if not isinstance(raw, dict):
        raise AgentConfigError('"network" must be an object')
    domains = raw.get("allow_domains", [])
    if not isinstance(domains, list) or not all(isinstance(d, str) and d.strip() for d in domains):
        raise AgentConfigError('"network.allow_domains" must be a list of host names')
    search = raw.get("search", False)
    if not isinstance(search, bool):
        raise AgentConfigError('"network.search" must be true or false')
    search_url = raw.get("search_url", "")
    if not isinstance(search_url, str) or (search_url and "{query}" not in search_url):
        raise AgentConfigError('"network.search_url" must be a URL containing {query}')
    return WebPolicy(tuple(domains), search, search_url)


def parse_hook_rules(raw: Any, section: str) -> tuple[HookRule, ...]:
    if not isinstance(raw, list):
        raise AgentConfigError(f'"hooks.{section}" must be a list')
    rules = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("tools"), str) or not isinstance(item.get("command"), str):
            raise AgentConfigError(f'each "hooks.{section}" entry needs "tools" and "command" strings')
        try:
            re.compile(item["tools"])
        except re.error as err:
            raise AgentConfigError(f'"hooks.{section}" tools pattern {item["tools"]!r}: {err}') from err
        rules.append(HookRule(item["tools"], item["command"]))
    return tuple(rules)


def parse_hooks(raw: Any) -> tuple[tuple[HookRule, ...], tuple[HookRule, ...]]:
    """The "hooks" section: {"before_tool": [{"tools": regex, "command": shell}], "after_tool": [...]}."""
    if not isinstance(raw, dict):
        raise AgentConfigError('"hooks" must be an object')
    return parse_hook_rules(raw.get("before_tool", []), "before_tool"), parse_hook_rules(raw.get("after_tool", []), "after_tool")


def parse_config(data: Any) -> AgentConfig:
    if not isinstance(data, dict):
        raise AgentConfigError("the file must contain a JSON object")
    commands = data.get("commands", {})
    if not isinstance(commands, dict):
        raise AgentConfigError('"commands" must be an object')
    rules = CommandRules(
        allow=tuple(parse_rule(r) for r in commands.get("allow", [])),
        deny=tuple(parse_rule(r) for r in commands.get("deny", [])),
    )
    sandbox = data.get("sandbox", False)
    if not isinstance(sandbox, bool):
        raise AgentConfigError('"sandbox" must be true or false')
    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise AgentConfigError('"mcp_servers" must be an object')
    plan_approval = data.get("plan_approval", True)
    if not isinstance(plan_approval, bool):
        raise AgentConfigError('"plan_approval" must be true or false')
    thinking = data.get("thinking", None)
    if thinking is not None and not isinstance(thinking, bool):
        raise AgentConfigError('"thinking" must be true or false')
    return AgentConfig(rules, sandbox, tuple(parse_mcp_server(name, raw) for name, raw in servers.items()),
                       plan_approval, parse_web(data.get("network", {})), *parse_hooks(data.get("hooks", {})),
                       thinking=thinking)


def with_default_search(config: AgentConfig, url: str) -> AgentConfig:
    """Use `url` as the search service when the project sets none; an empty or {query}-less url changes nothing."""
    if config.web.search_url or QUERY_FIELD not in url:
        return config
    return dataclasses.replace(config, web=dataclasses.replace(config.web, search_url=url))


def load_agent_config(root: str, io: Any) -> AgentConfig:
    if DEFAULT_SEARCH_URL and QUERY_FIELD not in DEFAULT_SEARCH_URL:
        io.tool_warning("Ignoring AIDER_AGENT_SEARCH_URL: it must contain {query}")
    return with_default_search(read_agent_config(root, io), DEFAULT_SEARCH_URL)


def read_agent_config(root: str, io: Any) -> AgentConfig:
    path = Path(root) / CONFIG_FILE_NAME
    if not path.is_file():
        return AgentConfig()
    try:
        return parse_config(json.loads(path.read_text(encoding=CONFIG_ENCODING)))
    except (OSError, ValueError) as err:
        io.tool_warning(f"Ignoring {CONFIG_FILE_NAME}: {err}")
        return AgentConfig()


def rule_as_json(rule: CommandRule) -> dict[str, Any]:
    data: dict[str, Any] = {"program": rule.program}
    if rule.subcommands:
        data["subcommands"] = list(rule.subcommands)
    if rule.trust_unsandboxed:
        data["trust_unsandboxed"] = True
    return data


def add_allow_rule(root: str, config: AgentConfig, rule: CommandRule) -> AgentConfig:
    """Append `rule` to the allow list in .aider-agent.json (created if missing); returns the updated config."""
    path = Path(root) / CONFIG_FILE_NAME
    data = json.loads(path.read_text(encoding=CONFIG_ENCODING)) if path.is_file() else {}
    data.setdefault("commands", {}).setdefault("allow", []).append(rule_as_json(rule))
    path.write_text(json.dumps(data, indent=2) + "\n", encoding=CONFIG_ENCODING)
    rules = CommandRules(allow=config.rules.allow + (rule,), deny=config.rules.deny)
    return dataclasses.replace(config, rules=rules)


def read_thinking(root: str) -> Optional[bool]:
    """The persisted `thinking` choice from .aider-agent.json, or None when unset, absent or unreadable."""
    path = Path(root) / CONFIG_FILE_NAME
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding=CONFIG_ENCODING)).get("thinking")
    except (OSError, ValueError):
        return None
    return value if isinstance(value, bool) else None


def write_thinking(root: str, enabled: bool) -> None:
    """Persist the `thinking` choice to .aider-agent.json (created if missing), leaving other settings intact."""
    path = Path(root) / CONFIG_FILE_NAME
    data = json.loads(path.read_text(encoding=CONFIG_ENCODING)) if path.is_file() else {}
    data["thinking"] = enabled
    path.write_text(json.dumps(data, indent=2) + "\n", encoding=CONFIG_ENCODING)


def instruction_files(root: str) -> list[str]:
    """Existing instruction files in the root, small enough to add to the chat."""
    found = []
    for name in INSTRUCTION_FILE_NAMES:
        path = Path(root) / name
        if path.is_file() and path.stat().st_size <= MAX_INSTRUCTION_BYTES:
            found.append(str(path))
    return found
