# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `--native-tools` flag: the model can call the read-only `read_file` and `list_files` tools through OpenAI-compatible native tool calling; results are sent back until the model answers without tools (at most 8 rounds). Implies `--no-stream`.
- `Model.send_completion()` accepts `tools` and `tool_choice` (defaults to `"auto"`) alongside the legacy `functions` path.
- Unit and mocked end-to-end tests under `tests/`.
- README, changelog, Apache 2.0 license, and a harness config that runs the tests and pins the commit email.
