# Tech debt and open work

This file lists the open work and known weak spots of aider-toolcalling, newest first.
Each item says what is known, what evidence exists, and what the next step is, so work can resume on any machine.
Remove an item when its fix is merged, and add new ones as they are found.

Last updated: 2026-11-19.

## Open

### 1. Agent loops on searches for code that does not exist (27B)

- **Merged as a safety net, not a proven fix:** `feature/repeat-second-chance` changes two things:
  - After 3 refused repeats, the model gets one more chance: a user message tells it to move on to the open tasks and the tests.
  - Refused call/refusal pairs are left out of the request.
- **Evidence:**
  - Long `/memory` task, single runs:
    - v0.8.0 and develop before #78 looped and changed nothing.
    - With the #78 nudge, one run changed 3 files.
    - Two runs with this branch looped and changed nothing.
  - Full 3x3 comparison on 2026-11-02 (develop vs branch, alternating, develop first in each pair): all 6 runs completed the task (5 files changed, tests passed). No repeat stop, move-on, forced answer, timeout or "say the word" in any run.
    - develop: 953, 750, 551 s; 32, 49, 29 tool calls; 243k, 532k, 240k tokens sent.
    - branch: 549, 516, 509 s; 24, 27, 25 tool calls; 152k, 215k, 169k tokens sent.
    - The branch's mechanisms never fired, so its lower time is not attributable to it; develop always ran first, so the branch may have reused a warm prompt cache.
    - Both sides predate #83 (v0.8.2), which refuses the first repeat of an unchanged read or of the command just run. Combined with this branch, the move-on message now comes after fewer identical calls (4 identical reads instead of 5). The combination is unit-tested and completed one long run (2026-11-02, before v0.8.3): 520 s, 23 tool calls, 173k tokens, 5 files, tests pass, no repeat stop or move-on.
  - Counting the 3 finished runs from 2026-10-30, 9 runs in a row completed without a loop. The loop is real but rare and depends on sampling.
- **Cross-turn loop fixed (2026-11-04):** the repeat guard was per request, so a model stopped for looping re-ran the same given-up search every time the user asked again ("are you working on this?"), and after the stop it answered in plain text that it was working without calling a tool. A refused code search is now remembered across turns until a file changes (`CROSS_TURN_GUARD_TOOLS` in `native_tool_loop.py`), and a no-tool-call reply that only promises action is sent back once (`announces_action` in `native_task_gates.py`). See the `## [Unreleased]` changelog entries.
- **Remaining failure mode:**
  - The model searched for `def root(` while `root` is an attribute (`self.root = ...`), and retried near-identical patterns. Near-identical patterns (same terms, other order or case) are still not caught as repeats, so the cross-turn memory does not yet cover them.
  - Twice it ended with "say the word and I'll proceed" even under `--yes-always`.
- **Next:**
  1. Watch for the loop in real sessions; when it happens, capture the request and replay it (see the end of this file).
  2. Ideas to try if it comes back:
     - ~~A "No matches" hint for `def X` searches: search for `X =` or use `find_symbol`.~~ Done (2026-11-04): `search_code` appends a hint when a `def NAME`/`class NAME` pattern finds nothing, naming the symbol and suggesting `NAME =`, a plain-name search or `find_symbol` (`definition_search_hint` in `aider/native_tools_search.py`). This targets the exact `def root(` → attribute case; watch whether it breaks the loop in a real session.
     - Treat near-identical search patterns as repeats. Not done: deferred as too likely to refuse distinct, valid searches (the same over-matching that had to be scoped back for the cross-turn guard).
  3. To rerun the comparison, recreate `compare_long.sh` from this description: per ref, a fresh detached worktree, `python -m aider.agent_main --yes-always --no-auto-commits --message "<the /memory task>"` with `PYTHONPATH` set to the worktree, then the task's tests; alternate the order of the refs to avoid the prompt-cache bias.

### 2. Heretic (8080) repetition in long /ask sessions

- A long `/ask` session on Heretic once produced repeated output. It did not reproduce in short tests: 0 of 6 runs with the old settings, 0 of 6 with the new.
- Defensive settings applied in `~/.aider.model.settings.yml`: max_tokens 8192, temperature 0.7, top_p 0.8, top_k 20, presence_penalty 1.5.
- **Largely addressed (2026-11-04):** the runaway-repetition failure this describes is now caught from two sides that did not exist when it was filed, the stream repetition guard (#110, trims a reply that collapses into the same line and sends it back) and `repetition_penalty: 1.05` on Heretic (added when `presence_penalty` was lowered to 0.5). Kept open only as a watch-item.
- **Next:** if it still recurs in a long real `/ask` session despite the guard and penalty, capture the request and replay it the way the 27B loop was found (see below).

### 3. Heretic (Qwen3.6 35B-A3B) wandered on a debugging task

- A session asked to fix a provider blocked by a Cloudflare check spent 25+ rounds and changed nothing.
- Fixed in the harness (v0.8.2): the prompt that read `a` as "no", messages typed at prompts, noisy risks for `2>/dev/null` and `| grep`, the missing working directory and venv, late repeat refusals, the grep exit 1 hint, and the search setup notice.
- **Still the model's:**
  - It said the challenge page returns HTTP 200 when its own curl showed 403.
  - It sent `Accept-Encoding: br` again after getting binary output.
  - It called `fetch_url` "with a proper User-Agent", though the tool takes no headers.
  - It read files one by one without a plan. Given a roadmap from the user, it went straight to a plan.
- **Rerun on v0.8.3 (2026-11-02, same prompt, unattended, every prompt approved; stopped by the user at 15 min):**
  - Planning is inconsistent: one run read and searched 32 times before its first plan, another planned first.
  - It never ran a request against 1337x. After 11 reads it added browser headers to `html_sites.json`, including `Accept-Encoding: gzip, deflate, br` (brotli is not in the project's requirements), and called them "Cloudflare-bypassing headers" without evidence. The earlier session had shown that a full browser header set still gets 403.
  - It searched for 1337x-specific code that does not exist (`def.*1337x`, `register_provider.*1337x`, `1337x.*cloudflare`); the site is a JSON entry built by a generic loader.
  - Harness issues found and fixed: a `cd <project root> &&` prefix on every command (compound and outside-the-project risks for nothing) and a garbled `todo_write` key `items"` (#91); every prompt failing with Errno 22 when stdin is `/dev/null` (#90).
- **Reruns on v0.8.4 (2026-11-03, same prompt, fresh detached worktree at the project's `HEAD`):**
  - Run 1, unattended (`--yes-always`, stdin `/dev/null`), stopped at 6 min: 14 reads, then the 1337x headers rewritten with a browser set including `Accept-Encoding: br`, without any request to the site, and called fixed. Its test command was declined: `--yes-always` never approves commands (`explicit_yes_required`), so an unattended run can run only commands that an allow rule in `.aider-agent.json` admits. Use a person at the prompt, or allow rules, for any run whose result depends on commands.
  - Run 2, with the "reproduce first" prompt line (#95), interactive: a plan after 15 reads, then `curl -sI` against 1337x before any edit (403, `cf-mitigated: challenge`). It then wrote `providers/cloudflare_bypass.py` (parse the challenge's JavaScript, replay cookies) and a `cloudflare_bypass` field in `spec.py`, and started on `factory.py` without running the bypass once. A managed challenge checks the browser itself, so this cannot work, and the project already raises `SiteDiscoveryError` for it on purpose.
  - Run 3, given the options (a headless browser service such as FlareSolverr, or a mirror): 13 reads in 9 min and a four-step FlareSolverr plan built on run 2's leftover `cloudflare_bypass` field. It never checked whether FlareSolverr was reachable (it was not running) or tried a mirror.
  - So the prompt line works (probe before edit), and the remaining gap is the model's: it commits to a fix before checking that the fix can work, and spreads it across files before running it.
  - Harness issues found: a fresh start overwrote the saved session (#97); near-duplicate searches (same terms, other order or case) are not caught by the repeat check; the tool log shows commands before the root `cd` is dropped.
  - Speed: on `mlx_vlm` every round re-processed the whole conversation (up to 103 s per round at 33k tokens; run 2 sent 340k tokens and received 1k). Heretic now runs on `mlx_lm` (#96).
- **Run on v0.8.5 (`mlx_lm`, interactive, same prompt, 48 calls in about 14 min, no edits):**
  - It probed the site after 4 calls (403), then tested candidates before writing anything: 9 curl commands, a loop over 6 domains, and a `task` sub-agent with `web_search` and `fetch_url`. It ended by listing options (a mirror; accept that 1337x is unusable from scripts; a headless browser; remove the entry), recommended the last two, and asked the user. Rounds took seconds: 50-2,300 new prompt tokens each, the rest from cache.
  - Still the model's: it took `1337x.unblockit.cat`, which redirects to a Sedo parking page with status 200, for "the actual 1337x content" and never checked the page for results. Its options still list parsing the Cloudflare challenge.
  - Harness issues found: the `task` sub-agent re-sent a declined `fetch_url` 8 times, because only the main loop stopped after repeated refusals (fixed in #101); a concurrent request from another session crashed the shared `mlx_lm` server (#100).
  - `--message` runs one request and exits, so a run that ends with a question cannot be answered; start without it to keep the conversation.
- **Next:**
  1. Prompt rule added (2026-11-04, #113), kept but unproven: the agent system prompt now says to test the cheapest form of an external dependency with one command before writing code, not to spread a fix across files until one run shows the approach can work, and that a 200 status is not proof (check the response holds what you expect). Same prompt-line mechanism as the #95 "reproduce first" line; a mechanical gate is not attempted because "the cheapest candidate" cannot be defined reliably.
     - **A/B validation (2026-11-04, Heretic on mlx_lm, 3 seeds each):** a benign task isolating the rule, an endpoint that returns HTTP 200 with an error body pointing at a moved path (`/prices` -> `/v2/prices`), fix discoverable only by probing the live service (mock kept out of the repo). With the rule: 3/3 probed before editing, 2/3 passed (the one miss was the command policy declining `curl <url>`, not the model). Without the rule (lines stripped): 3/3 probed, 3/3 passed. **The rule made no detectable difference**: Heretic reproduced with pytest, probed with `python -c urlopen`, saw the misleading 200, fixed the path and re-tested either way. Its baseline probe/verify discipline already handles a task with a clean discoverable fix; the rule is kept as a cheap, harmless nudge for genuinely harder cases but is not demonstrated to help.
     - **Why the benign task does not reproduce the original failure:** the 1337x case flailed because it had *no valid fix* (a managed Cloudflare challenge), so there was nothing a probe could converge on; a task with a real fix lets the model succeed with or without the nudge. A discriminating test would need a tempting-but-wrong obvious fix and a non-obvious real cause.
     - **Harness friction found:** the command policy declines `curl <url>` (the URL argument reads as risky) while allowing `python -c "...urlopen..."`; the model adapts by falling back to Python. Allow `curl` explicitly if an unattended run should use it.
  2. The "No matches" hint from item 1 was added (#112); it suggests the plain name or find_symbol. It does not yet say the name may be data or config rather than code, which is the 1337x case here.

### 4. Heretic (8080) ran out of GPU memory and used many tokens per round

- **What happened (2026-11-04):** a long agent session on Heretic grew to ~42K prompt tokens; `~/.cache/mlx-serve.log` showed `KV Caches: 10 seq` climbing from 16 GB to 27 GB, then `[METAL] ... Insufficient Memory` and the server crashed. KeepAlive relaunched it with a cold cache, so the next request reprocessed the whole ~32K prompt (the long wait the user saw).
- **Root cause:** `mlx_lm --prompt-cache-size` defaults to 10 (hold 10 distinct conversation caches); the LaunchAgents never set it, and `--prompt-cache-bytes 8 GB` did not bound the live KV caches in 0.31.3.
- **Done:** the example templates now pass `--prompt-cache-size 1` (`docs/examples/launchagents/local.mlx-lm-agent.plist`, `local.mlx-serve.plist`), documented in `docs/LOCAL_SETUP.md`. The harness itself is already cache-friendly: `compact_tool_history` changes nothing below ~48K tokens and `add_working_state` appends rather than splicing, so the prefix stays stable.
- **Applied (2026-11-04), live config only:**
  1. `--prompt-cache-size 1` added to the live `~/Library/LaunchAgents/local.mlx-lm-agent.plist` and `local.mlx-serve.plist`; 8083 booted out and back in to pick it up.
  2. `use_repo_map: false` set for all local models in `~/.aider.model.settings.yml`. The token drop was **not cleanly isolated**: a hard-set rerun sent ~11.2K tokens/task vs ~14K before, but that run also carried the #112/#113 changes, so the repo-map share is not separated. Measure it alone if it matters.
  3. Heretic `max_tokens` raised 8192 -> 16384 in `~/.aider.model.settings.yml`, for thinking-trace headroom; a hard-set eval at 16384 held 20/20 with no runaway loops.
- **Not propagated to the repo:** these live in the user's `~/.aider.model.settings.yml`; `docs/examples/aider.model.settings.yml` still ships the old values. Propagate there if a second Mac should inherit them.
- **Note:** per-round "tokens sent" is the full conversation by design (chat API); the prefix cache saves compute/time, not the displayed token count.

### 5. Expert eval set: results and what is still open (2026-11-18, repeat runs 2026-11-19)

- **Why:** the hard set saturated (20/20), so it no longer showed where the agent breaks. `evals/expert/` holds eight multi-file tasks with hidden checks and reference solutions (`--set expert --sandbox --timeout 2400`).
- **Results, one run per task, seed 1001** (before = v0.8.10; after = the `feature/expert-evals` branch, released as v0.9.0, latest valid run):

  | Task | 27B before | 27B after | Heretic before | Heretic after |
  |---|---|---|---|---|
  | api-migration | pass (at the 2,400 s limit) | pass, 601 s | fail | pass, 756 s |
  | circular-import | pass, 2,312 s | pass, 306 s | fail | pass, 564 s |
  | expr-eval | fail | pass (at the limit) | fail (timeout) | fail |
  | large-file | pass, 888 s | pass, 628 s | pass | pass, 125 s |
  | perf-dedupe | pass | pass | pass | pass, 126 s |
  | scheduler | pass, 861 s | pass, 628 s | pass, 477 s | pass, 1,252 s |
  | split-module | fail | pass, 772 s | fail | pass, 189 s |
  | todo-cli | not run | pass, 627 s | not run | pass, 633 s |
  | Total | 5/7 | 8/8 | 3/7 | 7/8 |

- **Read the table with these limits:**
  - One run per task is a sample, not a rate. On the branch the 27B's scheduler failed once and passed once, its circular-import failed once (before the `python -m` fix) and passed once, and Heretic's scheduler failed once (output limit) and passed once. Use `--repeat 3` before reading a single flip as a gain or a regression.
  - The before runs had two models loaded at once on a Mac about 50 GB into swap; the after runs had one model. Times are only roughly comparable.
  - The after runs were made on different commits of the branch as fixes landed, not all on its head.
- **Repeat runs, 2026-11-19** (`--repeat 3`, one model at a time, expr-eval once per model because it takes up to 40 minutes; v0.9.1 plus the eval-runner changes of 0.9.2):

  | Task | Heretic | 27B, chat settings | 27B, agent settings |
  |---|---|---|---|
  | api-migration | 3/3 (516 to 625 s) | 3/3 | not rerun |
  | circular-import | 3/3 (402 to 715 s) | 3/3 | not rerun |
  | large-file | 3/3 (132 to 406 s) | 3/3 | not rerun |
  | perf-dedupe | 3/3 (92 to 114 s) | 3/3 | not rerun |
  | split-module | 3/3 (459 to 608 s) | 3/3 | not rerun |
  | scheduler | 3/3 (186 to 651 s) | 1/3 | 3/3 (406 to 784 s) |
  | todo-cli | 3/3 (705 s, 1,165 s, one at the limit) | 0/3 | 2/3 (1,433 s fail, 1,860 s, one at the limit) |
  | expr-eval | 0/3 (two more runs on 2026-11-20) | 0/1 | 1/1 (1,106 s) |
  | Total | 21/24 | 16/22 | 6/7 |

  - **The "chat settings" column is not what `aider-agent` runs.** Until 0.9.2 the runner started `python -m aider --agent`, which does not load `~/.aider.agent.model.settings.yml`; the 27B ran with `max_tokens` 32768 and the chat sampling values. Two of its six failures were one runaway tool call each that held the server for about an hour. The five tasks at 3/3 were not repeated on the agent settings; the three that had failed were.
  - **27B agent settings for the rerun:** `max_tokens` 8192, `top_k` 20, `presence_penalty` 1.0, `repetition_penalty` 1.05, repo map off. The repetition penalty next to the presence penalty was new that day and showed no garbled code in 7 runs.
  - **Heretic's times** were measured while another project's servers ran on the same Mac; read them as upper bounds.
  - **Failures that are the model's:** Heretic's three expr-eval runs each miss a case SPEC.md states and the visible tests leave out (a `ValueError` on `.`, an "unexpected character", and `2 ** -1` rejected); each time it stopped once the visible tests passed and reported the spec as followed, without reaching the time or output limit. the 27B's failed todo-cli sorts `--sort due` wrongly and reported the order as checked.
  - **Passes at the limit:** both todo-cli runs that hit 2,400 s had a correct `todo.py` and were still verifying. Heretic kept running one command per reply; the 27B deleted its own passing check script and was sent back to verify again (fixed, see `## [Unreleased]`).
  - **Seen live in these runs:** the same-error note (27B, twice), the no-retry stop on a server timeout, `delete_file`/`move_file` (5 runs), and the unattended decline wording (26 declines in 29 runs, none fatal).
  - **Declined commands that remained after that round:** `CMD; echo "exit: $?"`, `CMD && echo OK`, `CMD || true`, a separator `echo "---"` inside a list (all four handled in 0.9.3), and, still declined by design, `rm -f` of a scratch file, paths under `/tmp` and `sh check.sh`.
- **Harness faults found and fixed** (see `## [Unreleased]`): verification commands written as `a && b`, multi-line `python -c` or a heredoc were declined (27 across the 13 before runs); `python -m MODULE` was not covered by a python rule; an unattended decline was reported as "the user declined"; no tool could delete or move a file; a reply that only promised work ended the request once the verify reminder was used; a `task` sub-agent reported command output it had worked out from the code; a reply cut at the output limit ended the request; one sampling seed for every request made a stuck model repeat itself exactly.
- **Every fix has now fired live.** On 2026-11-20 against Heretic, on a two-bug test project: with `max_tokens` 120 the output-limit send-back fired twice and the model went on to fix the code and pass the tests; a delegated `task` returned its report with the operation-log footer (`python -m pytest ... -> exit 0`, `Files changed: calc.py`). Logs: `evals/results/expert-20261120/live-cut.log` and `live-task.log`.
- **Open:**
  1. **mlx_lm keeps generating abandoned requests.** When a request timed out, the client retried and the server worked through every abandoned generation in turn (about 7 minutes each on the 27B). On 2026-11-18 this cost one run its last request and starved the next task completely (0 tool calls in 2,400 s).
     - **Fixed in the agent (2026-11-19):** a timed-out request is not sent again, and agent mode waits 1,800 s instead of 600 (`aider/native_request_timeout.py`). Checked live against the 27B with `--timeout 4`: one request, the stop message, exit after 10 s.
     - **Evals:** a task killed at its time limit leaves its last request generating on the server. Pass `--after-timeout CMD` with a command that restarts the model's server and waits for `/v1/models` (`launchctl kickstart -k gui/$(id -u)/local.mlx-lm-agent`, or `local.mlx-serve` for 8080); the runner runs it after every task that hits the limit.
  2. **expr-eval is one sample per model.** The 27B passed it in 1,106 s on the agent settings (2026-11-19) after a pass at the limit and a fail on the chat settings; the hour-long last requests of the earlier runs came from the chat `max_tokens` of 32768.
  3. **expr-eval fails on the model, and a spec reminder did not change that.** Heretic is 0/3 without it: it gets the visible tests passing and stops, without running the examples in SPEC.md.
     - **Tried on 2026-11-20, not merged; the branch was deleted and the code is not kept.** What it did: when the request names a document and the agent changed other files, the answer is sent back once asking it to run the document's own examples.
     - **Result:** expr-eval 0/3 on Heretic and 0/1 on the 27B (which had passed once without it). In Heretic's first run the reminder did what it was meant to: the model reran SPEC.md, hit `2 ** -1`, then broke the parser trying to fix it (`RecursionError`) and finished failing. In the other two it arrived after the model was already at the output limit. The 27B answered it with its own script that printed "ALL SPEC EXAMPLES PASSED" and missed `max(1)`.
     - **Cost on tasks that pass:** circular-import and todo-cli still passed on both models (4/4), but the 27B's circular-import took 981 s against about 300 s before, and Heretic's todo-cli ran to the 2,400 s limit.
     - **Reading:** finding the failing example is not the bottleneck; fixing it without breaking the rest is. One run per cell, so the cost figures are indications only.
  4. **Heretic reasons in prose at length** (about 1,350 log lines between two tool calls in its passing scheduler run). The output-limit send-back only catches the case that reaches the limit.
  5. **The verify gate accepts any passing command.** Heretic's before run of api-migration missed a caller, ran "all modules import OK" and was let through. No mechanical rule is known that would catch this without refusing honest checks.
  6. A command that contains `$` other than a trailing exit-status echo is still compound. The exit-status echo, `&& echo OK` and `|| true` tails are dropped before the command runs since 0.9.3, so the tool reports the real exit code; seen live on 2026-11-20 (`python todo.py ... ; echo "EXIT: $?"` ran and returned `exit 2`).
- **Running the set:** one model at a time, one results file per model, `--resume` to continue. Two models at once drain the battery and push the Mac into swap. Keep the Mac awake with `caffeinate -is`.

## Known limits (not planned)

- **mlx_lm buffers tool-call text**, so a model that loops inside a tool call shows nothing until `max_tokens`. The 27B needs `repetition_penalty: 1.05` (see `docs/examples/aider.model.settings.yml`).
  - Each machine's own `~/.aider.model.settings.yml` must carry it.
  - If a request hangs anyway, restart 8083 (`launchctl kickstart -k gui/$(id -u)/local.mlx-lm-agent`). The server keeps generating after the client gives up.
- **mlx_vlm (8081; Heretic's 8080 until 2026-11-03)** sometimes returns HTTP 500 "Thread group size (1024) is greater than the maximum allowed threads per threadgroup (896)". This is an upstream mlx bug.
- **mlx_lm 0.31.3 batching**: when two clients' requests arrived together (Heretic's agent and another repo's session, 2026-11-03), the server batched them and its generation thread died with `TypeError: 'NoneType' object is not iterable` in `logits_processors`; `/v1/models` still answered, but every later request hung until a restart. Both LaunchAgent templates now set `--decode-concurrency 1 --prompt-concurrency 1`, so a second client waits instead. Drop them only after checking a newer mlx_lm with two concurrent clients.
- **MCP OAuth** was checked against real Notion up to the browser step: discovery, registration, PKCE, and the scope from the 401. The code exchange and refresh are covered only by the fake server in `tests/test_mcp_oauth.py`.
- **Parallel `research` sub-agents** were measured slower than sequential ones (prompt cache reuse) and were not merged. Do not retry without a new reason.

## How the 27B loops were debugged

To see what the model generates inside a buffered tool call:

1. Put a logging proxy in front of 8083 and point a copy of the model settings at it.
2. Save each request body.
3. Render the messages with the tokenizer's chat template (`apply_chat_template` with the tools).
4. Replay the rendered prompt through `/v1/completions` with `logprobs: true`, then decode the token ids.

Variants of the request (messages removed, a user message added) can then be tested in seconds, without rerunning the agent.
