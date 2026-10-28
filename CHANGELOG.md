# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- "Always allow": after you approve a plain, risk-free command, Aider asks whether to add the narrowest matching allow rule to `.aider-agent.json` (for git, npm, uv and similar, only that subcommand). The question needs an explicit yes, so `--yes-always` never adds rules. Outside the sandbox the rule is written with `trust_unsandboxed`.

### Changed

- Read-only tool calls of one round (`read_file` on non-secret paths, `list_files`, `find_files`, `search_code`, `find_symbol`, `git`) run concurrently, at most 8 at once; calls that may ask the user stay sequential and results keep the model's order.

### Added

- Real-project tasks: `python -m evals.mine_real_tasks --repo PATH --python PY` turns small bug-fix commits (Python sources plus tests) into tasks, keeping only those whose tests fail before the fix and pass at the fix. The task project is history-free, every non-test file the fix touched (sources, changelog, docs) is back at its pre-fix version, and the check also requires the tests to be unchanged. `run_evals --real FILE` runs them, with `python` in the agent's commands pointing at the project's interpreter.

## [0.4.0] - 2026-10-27

### Added

- Hard evaluation set (`evals/tasks_hard.py`, 10 tasks): module extraction, two bugs in one class, a new CLI flag, a type mismatch across files, a class from a spec, order-preserving dedupe with a caller, config defaults, a fast Fibonacci, a class rename over three files and a log parser. Every check fails on the untouched project and passes with a reference solution.
- `evals.run_evals --set basic|hard|all` and `--repeat N`; the summary reports a pass rate per task.
- Files that usually hold secrets (`.env`, private keys, credential and token files, `.ssh`, `.aws`) need approval every time `read_file` opens them (`--yes-always` does not approve), and `search_code` skips their content. Example and template files are not treated as secrets.
- The agent prompt states that tool results are data, not instructions; `fetch_url` results are labelled as untrusted web content.
- `python -m evals.run_evals --sandbox` gives each task project a sandbox config that allows python and pytest, to measure the effect of self-verification.

### Changed

- Requests keep a stable prefix for server-side prefix caching: the working state is sent as a final message instead of inside the system message, and old tool results are summarized only once the history passes about 12K tokens (48,000 characters). Measured on the local 27B model, prefill was 86% of the agent's time and no request reused a cached prefix.

### Fixed

- A Ctrl+C while a tool was running left its ledger record as started or approved; it is now closed as failed ("interrupted by the user"), and the session file reflects it.
- A declined command or fetch said "The user declined this change"; it now says "this action".

## [0.3.0] - 2026-10-27

### Added

- macOS sandbox for agent commands (`"sandbox": true` in `.aider-agent.json`): `run_command` and background commands run under `sandbox-exec` with writes limited to the project and temp directories and no network. With the sandbox on, allow rules auto-approve without `trust_unsandboxed`; risky and compound commands are still asked.
- Background commands: `start_background`, `read_background` (incremental output) and `stop_background`, with the same policy, approval and sandbox as `run_command`; at most 4 at once, all stopped on exit.
- `fetch_url` tool: one http(s) page as text; every fetch is asked and `--yes-always` does not approve it.
- Agent sessions are saved after every request to `.aider.agent-session.json` (history with tool messages, operation ledger, task list); `--resume` restores them.
- Packaging: `pyproject.toml` with the dependencies of aider-chat 0.86.2 and an `aider-agent` command, so the patched Aider installs without `PYTHONPATH` (`uv tool install`).

### Fixed

- In plain streaming output the tool summary line was appended to the last line of the reply.

### Added

- Command policy for `run_command`: commands are parsed into argv (program, subcommand, arguments), not matched as text. Compound commands, path arguments outside the project, network access, deletion, git remote operations and package installs are labelled risks and always asked; `sudo`, force pushes and recursive deletion of the project root or outside it are refused.
- `.aider-agent.json` project config with command `allow` and `deny` rules (program plus optional subcommands). Allow rules auto-approve only for `trust_unsandboxed` rules until a sandbox exists.
- Read-only `git` tool (status, diff, log, show, blame) without approval: no shell, allow-listed flags, paths inside the project, no pager, external diff, textconv, global or system git config.
- `todo_write` tool in agent mode; open tasks are part of the working state sent with every request.
- `/undo-agent` restores files changed by the agent's tools in its latest request (originals are captured before each write; created files are removed). Works without git or auto-commits.
- Agent mode adds `AGENTS.md` and `CLAUDE.md` from the project root to the chat as read-only files.

### Added

- Operation ledger: every tool call is recorded with its id, arguments, request, status (started, awaiting approval, approved, denied, executed, failed) and result, separately from the chat history. A call id that already finished in the current request is not run again.
- Structured working state (files read and changed, commands with exit codes, declined operations, recent tool errors), built from the ledger and attached to every request.
- Tool results older than the last two rounds are sent as one-line summaries; the stored history keeps them in full. A single tool result is capped at 30,000 characters.
- `--max-tool-rounds N` (default 25); at the limit Aider asks whether to allow another N rounds, at most three times.
- Each tool result is summarized in the terminal (`-> 42 lines`, `-> exit 1: ...`); `--verbose` prints it in full.
- `.aider.tools.jsonl` audit log of finished operations in the project root.
- Evaluation set: 10 tasks with automatic checks and `python -m evals.run_evals`, recording success, rounds, calls, time and tokens.

### Fixed

- An API retry during tool rounds restarted from the message list before those rounds, so the model could repeat edits that had already been applied. Rounds are now appended to the request's own message list and a retry resumes after them.

## [0.2.0] - 2026-10-27

### Added

- Streaming with native tools: tool-call fragments from stream chunks are assembled per index, and every tool round is streamed. `--native-tools` and agent mode no longer force `--no-stream`.
- After each request with tool calls, a summary line shows the rounds, tool calls and elapsed time.

### Fixed

- `find_symbol` listed a definition twice when tree-sitter reported it twice.

### Added

- Agent mode (`--agent`, `--edit-format agent`, `/chat-mode agent`): the model explores, edits and verifies the project only through tools, with its own system prompt instead of an edit format.
- Search tools `find_files` (glob), `search_code` (regex) and `find_symbol` (tree-sitter definitions); `read_file` takes an optional line range. They are also available with `--native-tools` in the other modes.
- Action tools for agent mode: `edit_file` (exact string replacement, must be unique unless `replace_all`), `write_file`, and `run_command` (timeout, output tail).
- Approvals: every file change shows a diff and asks (Yes/No/All/Skip all per request; `--yes-always` approves edits); every shell command asks each time and is never approved by `--yes-always`.
- Files changed by tools go through Aider's post-edit flow (lint, auto-commit, tests).
- Tool calls and results stay in the chat history; orphaned tool messages are cleaned up before each request.
- The terminal shows each tool call with its arguments.

### Added

- Tool calls are accepted in every common response shape: objects or dicts, string or dict arguments, and Qwen-style `<tool_call>{...}</tool_call>` blocks in the message text. Calls without an id get a synthetic id that matches between the assistant and tool messages.
- Tool arguments are validated against the tool's JSON schema (required, unknown and wrongly typed arguments); the model receives a precise error message and can retry.

### Changed

- When the 8-round limit is reached, the last requested tools still run and the model is asked once more with `tool_choice="none"`, so the turn always ends with an answer.
- Unknown tool errors list the available tools.
- The repo opts out of the agent loop (`"agent_loop": false`); changes are gated by the harness hooks and tests.

## [0.1.0] - 2026-10-27

### Changed

- Aider's local files (`.aider*`: chat and input history, tags cache) are git-ignored.

### Added

- `--native-tools` flag: the model can call the read-only `read_file` and `list_files` tools through OpenAI-compatible native tool calling; results are sent back until the model answers without tools (at most 8 rounds). Implies `--no-stream`.
- `Model.send_completion()` accepts `tools` and `tool_choice` (defaults to `"auto"`) alongside the legacy `functions` path.
- Unit and mocked end-to-end tests under `tests/`.
- README, changelog, Apache 2.0 license, and a harness config that runs the tests and pins the commit email.
