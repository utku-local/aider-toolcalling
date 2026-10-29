# aider-toolcalling

A patched copy of the [Aider](https://github.com/Aider-AI/aider) 0.86.2 `aider` package that adds OpenAI-compatible
native tool calling, aimed at a local MLX model served by `mlx_lm`. With `--native-tools` the model can call
read-only project tools; Aider executes them, sends the results back and the final answer goes through Aider's
normal edit pipeline.

## Status

Working agent: read, search, git, edit, shell, background and fetch tools; command policy and sandbox; plan-first and verify-before-finishing checks; operation ledger, working state, sessions; streaming. Only the `aider/` package is tracked; it runs on top of an installed `aider-chat` 0.86.2, which provides
all dependencies.

## Setup

1. Install Aider 0.86.2 as a uv tool (provides the interpreter and dependencies):

   ```
   uv tool install --python 3.12 aider-chat==0.86.2
   ```

2. Clone this repo, for example to `~/aider-toolcalling-dev`.
3. Point Aider at the local model server in `~/.aider.conf.yml` (`model: openai/<model-id>`,
   `openai-api-base: http://127.0.0.1:<port>/v1`).

## Setting up a new Mac

`docs/LOCAL_SETUP.md` walks through the full local setup (model servers, LaunchAgents, aider configuration,
`aider-agent`), with templates in `docs/examples/`, including which model to run on a 32 GB Mac.
`docs/MODEL_COMPARISON.md` records why the 27B is the agent model, how Coder-Next compared, and that the 32 GB
M4 Air uses only the 27B (4-bit).

## Install as a command

```
uv tool install --python 3.12 git+https://github.com/UttyWotty/aider-toolcalling.git@main
aider-agent            # agent mode; any aider option works, e.g. --model, --resume, --chat-mode ask
```

`aider-agent` does not replace an existing `aider` command. From a clone, `uv tool install --python 3.12 .` installs
the working copy.

## Usage

Run the patched package from any project directory:

```
PYTHONPATH=~/aider-toolcalling-dev ~/.local/share/uv/tools/aider-chat/bin/python -m aider --native-tools
```

Agent mode, the closest to a local coding agent like Claude Code:

```
PYTHONPATH=~/aider-toolcalling-dev ~/.local/share/uv/tools/aider-chat/bin/python -m aider --agent
```

| Tool | Modes | Approval |
|---|---|---|
| `read_file`, `list_files`, `find_files`, `search_code`, `find_symbol` | `--agent`, `--native-tools` | none (read-only, confined to the project root); secret files such as `.env` or keys are asked every time and skipped by search |
| `edit_file`, `multi_edit`, `write_file` | `--agent` | diff shown; Yes/No/All/Skip all per request; `--yes-always` approves |
| `git` (status, diff, log, show, blame) | `--agent`, `--native-tools` | none (read-only, allow-listed flags) |
| `read_spreadsheet` | `--agent`, `--native-tools` | none (read-only; .xlsx/.xlsm sheets as text, in pages) |
| `todo_write` | `--agent` | none (the agent's task list) |
| `research` | `--agent` | none (a read-only sub-conversation that returns only its answer) |
| `run_command`, `start_background`, `read_background`, `stop_background` | `--agent` | command policy: refused, asked with risk labels, or allowed by a rule (trusted, or any rule inside the sandbox); `--yes-always` never approves a command |
| `fetch_url` | `--agent` | asked for every URL; `--yes-always` never approves it |

Files changed by tools are linted, auto-committed and tested like any Aider edit, following your settings.
`/undo-agent` restores the files the agent changed in its latest request, also without git.
Agent mode adds `AGENTS.md` / `CLAUDE.md` from the project root to the chat as read-only instructions.

Command rules live in `.aider-agent.json` in the project root:

```json
{"commands": {"allow": [{"program": "pytest", "trust_unsandboxed": true}],
              "deny": [{"program": "docker"}]}}
```

`"sandbox": true` runs commands under macOS `sandbox-exec`: writes only inside the project and temp directories, and
network only to localhost (services you run, such as a database, stay reachable; the internet is blocked). The agent
is told this in its system prompt, and a refused connection or a sandbox denial in command output gets a note naming
the likely cause, so the model reports a stopped service instead of debugging the code. Inside the sandbox every allow rule auto-approves; compound commands and risky programs are still asked.

Agent sessions are saved to `.aider.agent-session.json` after each request; `--resume` continues one with its tool
history, operation log and task list.

After you approve a plain command, Aider offers to remember it as a rule ("Always allow `pytest` in this
project?"); answering yes writes the rule to `.aider-agent.json`.

MCP servers (stdio) can be added in the same file; their tools appear as `mcp__<server>__<tool>` and each call is
asked unless the server is trusted:

```json
{"mcp_servers": {"docs": {"command": "npx", "args": ["-y", "some-mcp-server"], "env": {}, "trusted": false}}}
```

A rule matches the parsed program (`python -m pytest` counts as `pytest`) and optional `subcommands`. Compound
commands, paths outside the project and risky programs are asked even when a rule matches. Without
`trust_unsandboxed`, an allow rule does not auto-approve, because the agent can change the code the command runs.

`PYTHONPATH` is required: launching the `aider` command or running a script from elsewhere imports the unpatched
installed copy instead.

- `--native-tools` (default off) exposes the read-only and search tools in any chat mode.
- Works with and without streaming; tool calls are assembled from stream chunks.
- After a request with tool calls, Aider prints the number of rounds, calls and the elapsed time.
- Up to `--max-tool-rounds` (default 25) model/tool round trips per message; then Aider asks whether to continue
  (at most three times) or the model answers without tools.
- Every tool call is recorded in an operation ledger and in `.aider.tools.jsonl`; the model gets a working state
  built from it at the end of each request. Older tool results are sent as one-line summaries once the history
  grows (superseded file reads first, then other results, file contents last).
- The request prefix stays stable between rounds, so a server with prefix caching (for `mlx_vlm.server`:
  `APC_ENABLED=1`) only processes the new tokens of each round.
- Tool errors (unknown tool, invalid JSON, arguments that do not match the tool schema) are returned to the model,
  not raised.
- Structured `tool_calls` and Qwen-style `<tool_call>` blocks in the text are both understood.

## Structure

| Path | Purpose |
|---|---|
| `aider/native_toolcalling.py` | Tool registry, execution and tool result messages |
| `aider/native_tool_loop.py` | Pure helpers for one tool round |
| `aider/native_tool_calls.py` | Normalizes tool calls from any response shape |
| `aider/native_tool_schema.py` | Validates tool arguments against their JSON schema |
| `aider/native_tool_stream.py` | Assembles streamed tool-call fragments |
| `aider/native_tools_builtin.py` | Read-only `read_file` / `list_files` tools |
| `aider/coders/native_tool_rounds.py` | Drives the tool loop for a Coder |
| `aider/coders/agent_coder.py`, `agent_prompts.py` | Agent chat mode |
| `aider/coders/native_tool_setup.py` | Builds the tool registry and approvals for a Coder |
| `aider/native_tool_context.py` | Context and permission levels shared by the tools |
| `aider/native_tools_search.py`, `native_tools_edit.py`, `native_tools_shell.py` | Search, edit and shell tools |
| `aider/models.py`, `aider/coders/base_coder.py`, `aider/args.py`, `aider/main.py` | Small hooks into upstream Aider |
| `aider/native_tool_ledger.py`, `native_working_state.py` | Operation ledger and the working state built from it |
| `aider/native_command_policy.py`, `coders/native_agent_config.py` | Command policy and `.aider-agent.json` |
| `aider/native_tools_git.py`, `native_todo.py`, `native_snapshots.py`, `native_undo.py` | Git tool, task list, snapshots and `/undo-agent` |
| `aider/native_sandbox.py`, `native_tools_background.py`, `native_tools_fetch.py` | Sandbox, background commands, `fetch_url` |
| `aider/native_environment.py` | What the agent is told about its command environment, and hints on connection errors |
| `aider/native_task_gates.py` | Plan-first and verify-before-finishing checks, read from the operation ledger |
| `evals/scenarios.py`, `scenario_scoring.py`, `run_scenarios.py`, `compare_models.py` | Behaviour scenarios, their scoring, runner and model comparison |
| `aider/coders/native_session.py`, `aider/agent_main.py`, `pyproject.toml` | Session save and `--resume`, the `aider-agent` command, packaging |
| `aider/native_tool_compaction.py`, `native_tool_summary.py` | History compaction and one-line result summaries |
| `evals/` | Evaluation tasks (basic, hard, mined from real commits), metrics and runner |
| `tests/` | Unit and mocked end-to-end tests |

## Tests

Run from the repo root so the patched package is imported:

```
~/.local/share/uv/tools/aider-chat/bin/python -m unittest discover -s tests
```

## Evaluation

```
~/.local/share/uv/tools/aider-chat/bin/python -m evals.run_evals [--tasks fix-discount,find-the-bug] [--model M]
```

Runs the tasks in `evals/tasks.py` in temporary repos with `--agent --yes-always` (edits approved, commands not) and
writes one JSON line per task to `evals/results/`, plus a summary: success rate, rounds, calls, time, tokens.
`--sandbox` adds a sandbox config allowing python and pytest, so the agent can run its own checks.
`--set hard` (or `all`) selects the harder tasks in `evals/tasks_hard.py`; `--repeat N` runs each task N times and
reports a pass rate per task.

Real-project tasks come from your own bug-fix commits:

```
python -m evals.mine_real_tasks --repo ~/path/to/repo --python /path/to/its/python   # writes evals/real/<repo>.json
python -m evals.run_evals --real evals/real/<repo>.json --sandbox
```

The task project has no git history and the fix's non-test changes undone, so the agent cannot read the answer;
the check runs the fix's tests and requires them to be unchanged.

Behaviour scenarios check how the agent works, not only whether it passes: planning, re-testing after a failure,
and a stopped service.

```
python -m evals.run_scenarios [--model M] [--repeat 3]       # writes evals/results/scenarios-<time>/
python -m evals.compare_models --run 27B:hard:<stamp> --scenarios 27B:evals/results/scenarios-<time>
```

Each run is scored on order (plan, inspect, test, verify), what followed each failed call, success judged from the
project, time and tokens. `scripts/coder_next_server.sh start|stop|status` swaps the 8080 and 8083 servers for
Coder-Next on 8084 (64 GB Mac only).

## Faster agent rounds with mlx_lm

`mlx_lm.server` reuses the cached prompt when a request extends the previous one, which is exactly what agent rounds
do; `mlx_vlm.server` does not. Measured on the same 27B model, a real task took 237 s instead of 1,060 s. Run an
`mlx_lm` server on its own port and point only `aider-agent` at it with `~/.aider.agent.model.settings.yml` (same
model name, `extra_params.api_base` set to that port); plain `aider` keeps using its usual settings.

## Upstream updates

New Aider releases are imported into the `upstream` branch and merged into `develop`; see `docs/UPSTREAM.md`.

## License

Aider is licensed under the Apache License 2.0; see `LICENSE.txt`. The changes in this repo use the same license.
