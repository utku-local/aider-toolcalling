# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- The agent system prompt asks the model to reproduce a bug or failure with a command and read its real output before changing code (30 more tokens on Heretic's tokenizer, about 1% of the fixed prompt). In the v0.8.4 rerun of the 1337x Cloudflare task, Heretic rewrote the site's headers after 14 reads, without sending a single request to the site, and called it fixed.

## [0.8.4] - 2026-11-02

### Changed

- Imported upstream Aider releases are kept as `upstream-X.Y.Z` tags instead of an `upstream` branch, so the repository has only `main` and `develop`. `docs/UPSTREAM.md` describes the import with a temporary branch; `upstream-0.86.2` points at the old branch's last commit.
- A leading `cd <project root> &&` (or `;`) is dropped from `run_command` and `start_background` commands, since they already run in the root. Heretic prefixed every command with it, which made each one compound and outside the project, so `cd /root && pip list 2>/dev/null | grep curl` was asked with two risks; it now has none. A `cd` anywhere else is kept.
- Tool arguments with a stray-quoted key (`items"`) or an array or object sent as a JSON string are repaired before validation when the intended parameter is unambiguous. Heretic sent `todo_write` as `{"items\"": "[...]"}` twice in one run and lost a round each time.

### Fixed

- With stdin from `/dev/null` (a script or scheduled run without `--yes-always`), every approval prompt failed on macOS with `[Errno 22] Invalid argument`, which the model got as the tool result, so no command or plan was approved. prompt_toolkit cannot watch `/dev/null`; prompts now fall back to plain input, and end of input takes the prompt's default as it already did for piped input.

## [0.8.3] - 2026-11-02

### Changed

- After three refused repeats the model gets one more chance: a user message tells it to stop looking for what a search did not find and go on with the open tasks and the tests. Only after three more refusals is it asked for its answer. In a long session the first stop came before the model had run its tests.
- Refused repeat calls and their refusals are no longer sent back to the model, and an older copy of a note or working state is dropped where they meet. With several identical call/refusal pairs in its context the 27B kept making the same call whatever it was told; without them it wrote its plan and went on.
- The one-line `run_command` summary in the terminal (and in compacted history) now states how many lines the output had, e.g. `exit 0, 9 lines: <last line>`, so a loop over several targets no longer looks like a single result. For output spilled to a file, the count is that of the full output.

### Fixed

- `ask_user` declares its options as at most 6 plain strings in the tool schema, and a refused call says exactly what was wrong (too many options, which one is not a string, which one is empty). A 27B session sent invalid options on its first call and got only "options must be at most 6 non-empty strings".

## [0.8.2] - 2026-11-01

### Added

- `docs/TECH_DEBT.md`: open work, known limits and how the 27B loops were debugged, so work can resume on another machine.
- After you decline a command or network access, the agent asks what it should do instead; your reply goes to the model as a user message. Before, the tool result told the model to ask you, and a local model tried another approach instead.
- A reply of several words typed at an approval prompt (for example "I did not decline this, carry on") is passed to the model after that step, and the question is asked again. Before, a message typed while the agent was working landed in the next prompt and never reached the model.
- The system prompt names the working directory, the OS and how to run the project's Python (`uv run python`, `poetry run python` or `.venv/bin/python`). A model without it tried `cd /home/user` and checked the system pip, which lacks the project's packages.
- `grep` or `rg` that exits 1 with no output gets a note saying this means "no matches", not an error.
- "Web search is not set up" is shown to you in full, instead of only to the model.

### Changed

- Redirects to `/dev/null`, `2>&1`, and pipes into read-only filters such as `head`, `grep` or `wc` no longer make a command compound, and `/dev/null` no longer counts as a path outside the project. `pip list 2>/dev/null | grep x` was flagged with two risks; it now has none, so the prompt only appears for real risks.
- A repeat of an identical `read_file` on a file that has not changed, and a command run twice in a row, are refused at the first repeat instead of the third run.

### Fixed

- Typing `a` at a `(Y)es/(N)o` command prompt counted as a silent "no": the prompt accepted `all` and `skip` though it did not offer them. Each prompt now accepts only the answers it shows and asks again for anything else.

- A one-shot `--message` run no longer starts the background chat-history summary as it exits: the thread outlived the process and printed "Summarization failed ... cannot schedule new futures after shutdown" after long agent sessions.

## [0.8.1] - 2026-10-30

### Changed

- Shorter agent system prompt and tool descriptions: the fixed part of every request drops from about 3,560 to 2,610 tokens (v0.6.2 sent 2,850). On the hard set with the 27B (2 x 10 tasks), both sides pass 20/20; mean time per task drops from 183 to 141 s and tokens sent from 16.5k to 8.6k.
- The example model settings add `repetition_penalty: 1.05` for the Qwen3.8 27B: without it the model can repeat one line forever inside a tool call, which the server buffers, so the agent waits until `max_tokens` (about an hour at 32k).

### Fixed

- A model that repeats a call it already made now gets a user message telling it to take the next step: the note and refusal in the tool result did not stop the 27B from searching again and again for functions it had not written yet, and a user message did.
- The forced answer after the round limit or repeated calls adds a user message asking for a plain-text answer: with `tool_choice: "none"` alone the 27B still wrote a tool call and the answer came out empty.
- A repeated search showed "2 results" for "No matches." in the terminal; the repeat note is no longer counted.
- The environment note and skill list were added to the system reminder as well, so they reached the model twice.
- MCP OAuth asks for the scope a server's 401 names (`scope="..."` in `WWW-Authenticate`) when the config sets none; Notion and Linear name one.

## [0.8.0] - 2026-10-30

### Added

- `AIDER_AGENT_SEARCH_URL` sets the `web_search` service for every project without its own `network.search_url`; `scripts/searxng_server.sh` installs and runs a private SearXNG on 127.0.0.1:8888 (install, start, stop, enable at login).
- OAuth sign-in for HTTP MCP servers (`"oauth": true` or `{client_id, scope, callback_port}`): discovery, dynamic client registration, browser sign-in with PKCE, tokens stored in `~/.aider-agent/mcp-oauth.json` and refreshed on expiry or a 401.
- `/skill NAME [request]` runs the agent with a skill's instructions; `/skill` alone lists the skills.

## [0.7.0] - 2026-10-29

### Fixed

- The plan-first check applies only before the request's first file change; after a change it had added rounds (a model writing a verification script late in a task was stopped to write a plan).

### Added

- Plan approval: the first plan the agent writes with `todo_write` in a request is shown to the user for approval. A rejected plan is cleared and the model gets the user's note; until it writes a new plan, the plan-first check refuses file changes. `--yes-always` runs approve automatically; `"plan_approval": false` in `.aider-agent.json` turns it off.
- `ask_user` tool: the agent asks one question, optionally with up to six numbered choices, and continues with the answer; an unattended run tells it to decide and state its assumption.
- Read before edit: `edit_file`, `multi_edit` and `write_file` refuse to change an existing file the agent has not read in this session, or that changed on disk since it read it (another tool, an editor, the user). New files need no read, and the agent's own writes keep the record current.
- Long output is kept whole: a command or tool result over the limit is saved to `.aider-agent/outputs/` (git-ignored by its own `.gitignore`) and the model gets the first 4,000 and last 16,000 characters with the path, instead of a cut-off tail.
- Model-written context summary: when a request's history passes ~48K tokens, the model writes a summary of the older tool rounds (goal, findings, changes, commands, what remains) that replaces them in the live request and in `cur_messages`; the last two rounds stay verbatim. The summary stays in place, so later requests extend it and the prefix cache stays warm. If the model cannot write one, the one-line compaction applies as before.
- Web access settings: `"network": {"allow_domains": [...]}` in `.aider-agent.json` lets `fetch_url` read those hosts (exact or `*.domain`) without asking; other URLs still ask. The example config allows docs.python.org, pypi.org and *.readthedocs.io.
- `web_search` tool: queries the search service named by `"network.search_url"` (SearXNG JSON format, for example a local SearXNG) and returns titles, URLs and snippets; each search asks unless `"network.search": true`. Without a service the tool tells the model search is not set up.
- Hooks: `"hooks": {"before_tool": [...], "after_tool": [...]}` in `.aider-agent.json` runs a command around tools whose name matches a pattern. A failing before hook blocks the call with its output as the reason; an after hook's output is appended to the result. The project's hooks are shown once per session and run only on an explicit yes, never in `--yes-always` runs, since a cloned repo could define any command.
- `remember` tool: saves a dated one-line project fact to `.aider-agent/memory.md`, which later sessions read like `AGENTS.md`.
- Skills: Markdown files in `.aider-agent/skills/` (project) and `~/.aider-agent/skills/` (user) are listed in the system prompt by their first line; `use_skill` loads one.
- `task` tool: delegates a self-contained job to a sub-agent with every tool except `ask_user` and `task` (up to 30 rounds); its edits and commands go through the usual approvals, hooks and output spill, and only its report returns to the main conversation.
- Background exit notices: when a process started with `start_background` exits on its own, the next request says so once (id, command, exit code), so the model does not have to poll `read_background`.
- `read_file` reads Jupyter notebooks (each cell with its text outputs) and PDFs (through poppler's `pdftotext`, no new Python dependency); images and other binary files are refused with a short reason instead of being returned as garbage.
- MCP over Streamable HTTP: an `mcp_servers` entry with `"url"` (and optional `"headers"`, whose values may use `${ENV_VAR}`) is reached by POSTing JSON-RPC; JSON and event-stream replies are both read, and the session id from `initialize` is sent with later requests. Stdio and HTTP share one `MCPSession` base for initialize, tools/list and tools/call.

### Changed

- Only `.aider-agent/outputs/` is git-ignored now (its own `.gitignore`), so memory and skills in `.aider-agent/` can be committed.
- The tool loop's optional behaviour (plan check, output spill, hooks) is passed as one `LoopOptions` object.

## [0.6.2] - 2026-10-29

### Added

- Behaviour scenarios for the agent (`evals/scenarios.py`, `evals/scenario_scoring.py`, `python -m evals.run_scenarios`): planning, re-testing after a failure and a stopped service, scored separately on order, error handling, task success, time and tokens. `python -m evals.compare_models` turns eval results and scenario folders into comparison tables. Declined test commands do not count as tests run, and the service scenario accepts starting the server as well as telling the user.
- `docs/MODEL_COMPARISON.md`: the 27B versus Qwen3-Coder-Next measurements and the decision to keep the 27B as the agent model, with a section for the 32 GB M4 Air (27B 4-bit only).
- `scripts/coder_next_server.sh start|stop|status`: runs Qwen3-Coder-Next on 8084 by hand on the 64 GB Mac, stopping 8080 and 8083 while it runs.

### Fixed

- Starting or stopping a background process (`start_background`, `stop_background`) resets the repeat count, like a file change. In a trial the model started a stopped server and was then refused re-running the client that had failed against it.

## [0.6.1] - 2026-10-29

### Fixed

- Integer tool parameters (line numbers, timeouts, row counts) are sent to the model as numbers described as whole numbers, and values like `120.0` are turned back into integers before validation. mlx_lm's `qwen3_coder` tool parser silently dropped any call whose "integer" value read `120.0`, so Qwen3-Coder-Next appeared to announce a step and then stop.
- An identical `todo_write` repeated in one request is refused like other repeated calls; Qwen3-Coder-Next had sent the same plan 98 times.

## [0.6.0] - 2026-10-29

### Added

- Plan first: when the agent tries to change a file after exploring (three or more tool calls in the request) without a task list, the change is refused once and it is asked to write a plan with `todo_write`, ending with how it will verify the result. A direct one- or two-step fix is not affected.
- Verify before finishing: when the agent answers after changing files and no command has passed since its last change, or its task list still has open items, the answer is sent back once with what is missing. In a trial session the agent had called an untested project "ready to use".
- The system prompt asks the agent to learn how a project runs (entry points, dependencies, services, tests) before planning, and never to call something working until a command shows it.

## [0.5.5] - 2026-10-29

### Changed

- The sandbox allows network connections to localhost (and local servers started by a command); the internet stays blocked. Before, every TCP connection was denied, so tests could not reach a database or download daemon the user runs.
- The agent's system prompt says where commands run (sandbox: writes, localhost, no internet; or no sandbox), to check that a needed service is running before debugging a connection error, and to tell the user what is missing instead of working around it.
- A failed command whose output shows a refused connection gets a note that the service is probably not running; in the sandbox, an "Operation not permitted" failure gets a note that the sandbox likely blocked it.
- A call the user already declined in the same request is refused without asking again, and counts toward ending the tool loop. A local model had sent one declined command more than 30 times, because declined calls were never counted as repeats.
- After four failing commands in a row in one request, the agent is told to stop, summarize what it tried and ask the user. In a trial session the model spent half an hour retrying connections that the sandbox and a stopped `aria2c` refused.

## [0.5.4] - 2026-10-29

### Changed

- `edit_file` and `multi_edit` accept an `old_string` that differs from the file only in trailing spaces or tabs on its lines. When nothing matches, the error names the first line that differs (or says the first line is not in the file). In a trial session the model failed the same multi-line edit twice and spent five rounds searching.
- A trailing `2>&1` is dropped from `run_command` commands, since stdout and stderr are already returned together; it no longer makes a command compound and ask for approval.
- Agent edit approvals no longer offer "(D)on't ask again", which in Aider means "never, and answer no"; a user pressed it expecting "always yes" and the edit was declined. "(A)ll" approves the remaining edits of the request.
- The `tests` workflow runs only when started by hand (`workflow_dispatch`) until the account's Actions billing is fixed; on push and pull request the jobs were refused before starting and showed as failures. Tests still run locally (`harness-check`) before every merge.

## [0.5.3] - 2026-10-29

### Changed

- An edit call (`edit_file`, `multi_edit`, `write_file`) identical to one already applied in the same request is refused and the model is told to read the file first; refusals count toward ending the tool loop. On a real task the agent sent one edit 70 times, and because its new text contained the old text each call added the same line again.

## [0.5.2] - 2026-10-29

### Added

- `docs/LOCAL_SETUP.md`: step-by-step setup of a Mac (mlx_lm server on 8083 at login, optional manual mlx_vlm server on 8081, aider configuration, `aider-agent`, checks and troubleshooting), with templates in `docs/examples/` for the LaunchAgents, `~/.aider.conf.yml`, model settings, model metadata and `.aider-agent.json`.

### Changed

- A read-only tool call (read, list, find, search, symbol, git) that already ran twice with the same arguments in one request is refused with an error telling the model to edit, run tests or answer; after three refusals the tool loop stops and asks for the final answer. On a real task the agent had re-read one file range 66 times despite the repeat note.
- The same repeat limit now covers `run_command`, and the count restarts after every file change (`edit_file`, `multi_edit`, `write_file`), so rerunning tests after an edit is never refused. On a real task the agent had run one passing test command 100 times without changing a file.

### Fixed

- `multi_edit` changes are listed under "Files changed" in the working state.

## [0.5.1] - 2026-10-28

### Added

- `aider-agent` loads `~/.aider.agent.model.settings.yml` when it exists, so agent mode can use its own model server (for example `mlx_lm.server` with prefix caching on another port) while plain `aider` keeps its settings.

### Changed

- Compaction starts only past ~48K tokens of history and then brings it to ~24K in one step, instead of summarizing from ~6K.
- Working-state messages already sent stay in the request, and a new one is added only when the state changes, so every request extends the previous one.
- Measured on the local 27B model: `mlx_vlm.server` cannot reuse a cached prefix for an extended prompt, so each agent round re-processed 5-11K tokens (1.5-3.5 minutes). `mlx_lm.server` reuses it when the new prompt strictly extends the old one; with these changes most rounds processed 30-1,100 new tokens. A real task went from 1,060 s to 237 s, and the hardest real task, which had failed at 40 minutes, passed in 400 s.

## [0.5.0] - 2026-10-28

### Added

- `read_spreadsheet` tool (read-only, in agent mode, `--native-tools` and `research`): lists the sheets of an .xlsx/.xlsm workbook and returns rows of one sheet as text, 50 at a time by default. Dates are shown as ISO dates, formulas without a saved result as their formula. Uses only the standard library; old .xls files are refused with a hint.
- Upstream updates: an `upstream` branch holds the untouched aider-chat source (0.86.2 imported from PyPI), `python -m maintenance.import_upstream VERSION --into DIR --pyproject FILE` imports a release and its pinned dependencies, and `docs/UPSTREAM.md` describes the merge procedure.
- CI: a GitHub Actions workflow installs the package with its pinned dependencies and runs the test suite on pushes to `main` and `develop` and on pull requests (macOS-only sandbox tests skip on Linux).
- `research` tool in agent mode: answers a question about the project in a separate conversation with read-only tools (at most 10 rounds) and returns only the answer, so the files it reads never enter the main conversation's prompt.
- MCP tools: stdio MCP servers listed under `mcp_servers` in `.aider-agent.json` start with agent mode, and their tools appear as `mcp__<server>__<tool>`. Each call asks first unless the server is `"trusted": true`; a server that cannot start is reported and skipped. Built on a small JSON-RPC client, no new dependency.
- `multi_edit` tool: several exact replacements in one file, applied in order with one diff and one approval; if any replacement fails, nothing is written.
- "Always allow": after you approve a plain, risk-free command, Aider asks whether to add the narrowest matching allow rule to `.aider-agent.json` (for git, npm, uv and similar, only that subcommand). The question needs an explicit yes, so `--yes-always` never adds rules. Outside the sandbox the rule is written with `trust_unsandboxed`.
- `--seed N` sends a sampling seed with every request; `run_evals` gives run k the seed `--seed-base` + k (default 1000). The local server used a fixed default seed when none was sent, so repeated runs had been identical.
- Evals keep each task's full agent output next to the results, for diagnosis.
- Real-project tasks: `python -m evals.mine_real_tasks --repo PATH --python PY` turns small bug-fix commits (Python sources plus tests) into tasks, keeping only those whose tests fail before the fix and pass at the fix. The task project is history-free, every non-test file the fix touched (sources, changelog, docs) is back at its pre-fix version, and the check also requires the tests to be unchanged. `run_evals --real FILE` runs them, with `python` in the agent's commands pointing at the project's interpreter.

### Changed

- Agent mode caps the repo map at 1,024 tokens and drops Aider's 8x multiplier for chats without files; on a real project the first prompt went from 10,367 to about 3,400 tokens.
- `read_file` without a line range returns at most 120 lines of a longer file and says how to read on.
- Compaction keeps the latest read of every file: superseded reads are summarized first, other tool results past ~6K tokens of history, file contents only past ~24K. A repeated identical read-only call gets a note that its result is already in the conversation. On a real task the agent had re-read the same files 26 times after their contents were compacted.
- The agent is told to run commands without pipes or redirections (output is already captured), so allow rules can match them.
- Read-only tool calls of one round (`read_file` on non-secret paths, `list_files`, `find_files`, `search_code`, `find_symbol`, `git`) run concurrently, at most 8 at once; calls that may ask the user stay sequential and results keep the model's order.

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
