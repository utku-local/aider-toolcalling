# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
