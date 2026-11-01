# Tech debt and open work

This file lists the open work and known weak spots of aider-toolcalling, newest first.
Each item says what is known, what evidence exists, and what the next step is, so work can resume on any machine.
Remove an item when its fix is merged, and add new ones as they are found.

Last updated: 2026-11-01 (after v0.8.2).

## Open

### 1. Agent loops on searches for code that does not exist (27B)

- **Branch:** `feature/repeat-second-chance` (pushed, no PR yet). It changes two things:
  - After 3 refused repeats, the model gets one more chance: a user message tells it to move on to the open tasks and the tests.
  - Refused call/refusal pairs are left out of the request.
- **Evidence:**
  - Long `/memory` task, single runs:
    - v0.8.0 and develop before #78 looped and changed nothing.
    - With the #78 nudge, one run changed 3 files.
    - Two runs with this branch looped and changed nothing.
  - In the 3x3 comparison (develop vs branch, 3 runs each), the first 3 finished runs (develop 2, branch 1) all completed the task: 5 files changed, tests passed, no loop. The loop depends on sampling.
- **Remaining failure mode:**
  - The model searched for `def root(` while `root` is an attribute (`self.root = ...`), and retried near-identical patterns.
  - Twice it ended with "say the word and I'll proceed" even under `--yes-always`.
- **Next:**
  1. Rerun the comparison to completion: `compare_long.sh` (3 runs of each ref). It lived in the session scratchpad; recreate it from this description if it is gone.
  2. Merge the branch only if it is not worse than develop.
  3. Ideas to try:
     - A "No matches" hint for `def X` searches: search for `X =` or use `find_symbol`.
     - Treat near-identical search patterns as repeats.

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
- **Next:** rerun the same task with the fixes. If it still reads without a plan, try a one-line "plan first for debugging tasks" in the system prompt and measure its token cost (see v0.8.1).

## Known limits (not planned)

- **mlx_lm buffers tool-call text**, so a model that loops inside a tool call shows nothing until `max_tokens`. The 27B needs `repetition_penalty: 1.05` (see `docs/examples/aider.model.settings.yml`).
  - Each machine's own `~/.aider.model.settings.yml` must carry it.
  - If a request hangs anyway, restart 8083 (`launchctl kickstart -k gui/$(id -u)/local.mlx-lm-agent`). The server keeps generating after the client gives up.
- **mlx_vlm (8080)** sometimes returns HTTP 500 "Thread group size (1024) is greater than the maximum allowed threads per threadgroup (896)". This is an upstream mlx bug.
- **MCP OAuth** was checked against real Notion up to the browser step: discovery, registration, PKCE, and the scope from the 401. The code exchange and refresh are covered only by the fake server in `tests/test_mcp_oauth.py`.
- **Parallel `research` sub-agents** were measured slower than sequential ones (prompt cache reuse) and were not merged. Do not retry without a new reason.

## How the 27B loops were debugged

To see what the model generates inside a buffered tool call:

1. Put a logging proxy in front of 8083 and point a copy of the model settings at it.
2. Save each request body.
3. Render the messages with the tokenizer's chat template (`apply_chat_template` with the tools).
4. Replay the rendered prompt through `/v1/completions` with `logprobs: true`, then decode the token ids.

Variants of the request (messages removed, a user message added) can then be tested in seconds, without rerunning the agent.
