# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
