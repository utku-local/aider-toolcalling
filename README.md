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
`docs/TECH_DEBT.md` lists open work and known limits; check it before starting something new.

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
| `todo_write` | `--agent` | none (the agent's task list); the first plan of a request is shown for approval unless `"plan_approval": false` |
| `ask_user` | `--agent` | none (asks you one question, with numbered choices; unattended runs get no answer) |
| `research` | `--agent` | none (a read-only sub-conversation that returns only its answer) |
| `task` | `--agent` | the sub-agent's edits and commands are approved as usual (a delegated job with every tool but `ask_user` and `task`; only its report returns) |
| `web_search` | `--agent` | network: asked unless `"network": {"search": true}`; needs `"search_url"` or `AIDER_AGENT_SEARCH_URL` |
| `remember`, `use_skill` | `--agent` | none (`.aider-agent/memory.md`; skills from `.aider-agent/skills/` and `~/.aider-agent/skills/`) |
| `run_command`, `start_background`, `read_background`, `stop_background` | `--agent` | command policy: refused, asked with risk labels, or allowed by a rule (trusted, or any rule inside the sandbox); `--yes-always` never approves a command |
| `fetch_url` | `--agent` | asked for every URL; `--yes-always` never approves it |

Files changed by tools are linted, auto-committed and tested like any Aider edit, following your settings.
`/undo-agent` restores the files the agent changed in its latest request, also without git.
Agent mode adds `AGENTS.md` / `CLAUDE.md` from the project root to the chat as read-only instructions.

For a reasoning model, `--agent-think` turns on its thinking trace (`--no-agent-think` turns it off), and `/think on | off | status` toggles it during a session without restarting the server. The choice persists per project in `.aider-agent.json` as `"thinking": true|false`; the CLI flag overrides it, which overrides the model's own default.

Command rules live in `.aider-agent.json` in the project root:

```json
{"commands": {"allow": [{"program": "pytest", "trust_unsandboxed": true}],
              "deny": [{"program": "docker"}]}}
```

`"network"` controls web access: `"allow_domains"` lists hosts (`"pypi.org"`, `"*.readthedocs.io"`) that
`fetch_url` reads without asking, `"search_url"` names a search service in SearXNG's JSON format
(`"http://127.0.0.1:8888/search?q={query}&format=json"`) for `web_search` (the `AIDER_AGENT_SEARCH_URL`
environment variable sets it for every project; `scripts/searxng_server.sh` runs a local SearXNG, see
[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md)), and `"search": true` stops each search from asking. `"plan_approval": false` turns off the plan approval prompt.

`"hooks"` runs your commands around tool calls: `{"before_tool": [{"tools": "edit_file|write_file", "command":
"./check.sh"}], "after_tool": [...]}`. A before hook that exits non-zero blocks the call and its output is the
reason; an after hook's output is added to the result. The hooks are shown once per session and run only if you
say yes; `--yes-always` runs never run them. Each gets `AIDER_TOOL`, `AIDER_TOOL_ARGS` and (after)
`AIDER_TOOL_RESULT` in its environment.

The agent can `remember` project facts in `.aider-agent/memory.md`, read at the start of later sessions, and load
skills: Markdown files in `.aider-agent/skills/` or `~/.aider-agent/skills/` whose first line describes them.
You can also start one yourself: `/skill` lists them, `/skill release 0.8.0` sends the `release` skill's
instructions with `0.8.0` as the request.

`"sandbox": true` runs commands under macOS `sandbox-exec`: writes only inside the project and temp directories, and
network only to localhost (services you run, such as a database, stay reachable; the internet is blocked). The agent
is told this in its system prompt, and a refused connection or a sandbox denial in command output gets a note naming
the likely cause, so the model reports a stopped service instead of debugging the code. Inside the sandbox every allow rule auto-approves; compound commands and risky programs are still asked.

Agent sessions are saved to `.aider.agent-session.json` after each request; `--resume` continues one with its tool
history, operation log and task list. Starting without `--resume` keeps the saved session as
`.aider.agent-session.previous.json` on the first save; rename it back to resume it.

After you approve a plain command, Aider offers to remember it as a rule ("Always allow `pytest` in this
project?"); answering yes writes the rule to `.aider-agent.json`.

MCP servers can be added in the same file, started over stdio (`command`) or reached over Streamable HTTP (`url`,
with `headers` whose values may use `${ENV_VAR}`); their tools appear as `mcp__<server>__<tool>` and each call is
asked unless the server is trusted:

```json
{"mcp_servers": {"docs": {"command": "npx", "args": ["-y", "some-mcp-server"], "env": {}, "trusted": false},
                 "remote": {"url": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer ${MCP_TOKEN}"}},
                 "signin": {"url": "https://mcp.example.org/mcp", "oauth": true}}}
```

`"oauth": true` signs in with OAuth (authorization code + PKCE, as the MCP spec describes): on the first 401 the agent
discovers the authorization server, registers itself as a client, opens your browser and catches the redirect on a
local port. Tokens are kept in `~/.aider-agent/mcp-oauth.json` (mode 0600) and refreshed when they expire. For a
server without dynamic registration, give the pre-registered client instead:
`"oauth": {"client_id": "...", "scope": "...", "callback_port": 8765}`.

`read_file` also reads Jupyter notebooks (cells with outputs) and PDFs (through poppler's `pdftotext`: `brew install
poppler`); images and other binary files are refused with a short reason, since the model reads text only.

A rule matches the parsed program (`python -m pytest` counts as `pytest`) and optional `subcommands`. Compound
commands, paths outside the project and risky programs are asked even when a rule matches. Without
`trust_unsandboxed`, an allow rule does not auto-approve, because the agent can change the code the command runs.
Redirects to `/dev/null`, `2>&1`, and pipes into read-only filters (`head`, `tail`, `grep`, `rg`, `wc`, `cut`,
`sort`, `uniq`, `tr`, `jq`, `nl`, `column`) are not compound: `pytest -q 2>&1 | tail -20` matches a `pytest` rule,
and the risks of every stage still count.

An approval prompt accepts only the answers it shows (`(Y)es/(N)o` takes yes or no) and asks again for anything else.
A reply of several words typed at a prompt is not an answer: it is passed to the model as a message from you after
that step, and the question is asked again. After you decline a command, the agent asks what to do instead; your
reply reaches the model the same way (Enter skips it).

The system prompt names the working directory, the OS and how to run the project's Python (`uv run python` with
`uv.lock`, `poetry run python` with `poetry.lock`, or `.venv/bin/python`), so the model does not guess paths or use
the system pip. An identical `read_file` of a file that has not changed, or the same command run twice in a row, is
refused at the first repeat.

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

New Aider releases are imported as `upstream-X.Y.Z` tags and merged into `develop`; see `docs/UPSTREAM.md`.

## License

Aider is licensed under the Apache License 2.0; see `LICENSE.txt`. The changes in this repo use the same license.
