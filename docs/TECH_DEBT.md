# Tech debt and open work

This file lists the open work and known weak spots of aider-toolcalling, newest first.
Each item says what is known, what evidence exists, and what the next step is, so work can resume on any machine.
Remove an item when its fix is merged, and add new ones as they are found.

Last updated: 2026-11-03 (after v0.8.7).

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
- **Next:** watch for it in a long real `/ask` session; if it comes back, capture the request and replay it the way the 27B loop was found (see below).

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
- **Pending (needs a server restart, so the user times it):**
  1. Apply `--prompt-cache-size 1` to the live `~/Library/LaunchAgents/local.mlx-lm-agent.plist` and `local.mlx-serve.plist`, then `launchctl bootout`/`bootstrap`.
  2. Try `use_repo_map: false` for the agent model: the repo map is a large fixed block re-sent every round, and agent mode already has `search_code`/`find_symbol`/`find_files`. Measure the token drop.
  3. Revisit `max_tokens: 8192` once thinking is enabled (`/think on`): the reasoning trace shares the output budget and can truncate the answer; try 16384 with thinking on.
- **Note:** per-round "tokens sent" is the full conversation by design (chat API); the prefix cache saves compute/time, not the displayed token count.

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
