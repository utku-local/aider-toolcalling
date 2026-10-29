# Agent model comparison (2026-10-29)

Two abliterated local models were measured as the `aider-agent` model on the 64 GB M1 Max, both served by
`mlx_lm.server` with the same agent code (v0.6.0/v0.6.1), the same flags and the same seeds:

| Name | Model | Size in memory | Served on |
|---|---|---|---|
| 27B | `ailexleon/Huihui-Qwen3.8-27B-abliterated-mlx-6Bit` (dense) | up to ~27 GB | 8083, at login |
| Coder-Next | `veeceey/Huihui-Qwen3-Coder-Next-abliterated-mlx-4bit` (80B MoE, 3B active) | ~44 GB | 8084, by hand |

**Decision: the 27B stays the default agent model.** Coder-Next stays available by hand on the 64 GB Mac only
(`scripts/coder_next_server.sh start`, then `aider-agent --model coder`).

## Results

| Model | Set | Passed | Time per success | Tokens per success | Answers sent back to verify |
|---|---|---|---|---|---|
| 27B | hard (10 tasks x 2) | **20/20** | 139 s | 12k | 16/20 |
| Coder-Next | hard (10 tasks x 2) | 18/20 | **52 s** | 30k | 10/20 |
| 27B | real (10 tasks) | **8/10** | 730 s | 303k | 0/10 |
| Coder-Next | real (10 tasks) | 7/10 | **331 s** | 420k | 0/10 |

Behaviour scenarios, three seeds each:

| Scenario | 27B | Coder-Next |
|---|---|---|
| Planning (add a feature with tests): success | 3/3 | 3/3 |
| Planning: plan written without the plan-first gate | 0/3 | **3/3** |
| Re-test (two bugs): test command actually ran after the fix | **3/3** | 0/3 |
| Service (server not running): solved without changing code | 3/3 | 3/3 (once by starting the server itself) |

Coder-Next is 2.2 to 2.7 times faster and plans without being asked, but it fails in ways the 27B does not:

- With a requirement stated rather than asked for (`load(path) must merge ...`), it asks the user what to do and
  stops, in both runs.
- It prefixes commands with an invented `cd /project && ...`, so its test runs are refused or fail.
- On one real task it reasoned in plain text until it hit the 8,192-token reply limit without calling a tool.
- It uses 1.4 to 2.5 times more tokens per successful task.

The 27B also passed every hard task with the plan-first and verify-before-finishing checks on, and needed the
verify reminder in 16 of 20 hard runs: it rarely runs the tests unprompted on short tasks.

Caveats: real tasks ran once per model, so one task either way is within noise; the 27B real tasks ran on v0.6.0
and Coder-Next on v0.6.1, whose two fixes (integer parameters, repeated `todo_write`) never triggered on the 27B;
the 27B hard set started with a cold prompt cache. The re-test scenario prompt was "The mean in stats/summary.py is
off by one. Fix it."; the 27B fixed the mean, ran the tests and called the remaining median failure out of scope.
The prompt now says "Make all of them pass", so later runs are not directly comparable on that row.

## Fixes found by the trial

- mlx_lm's `qwen3_coder` tool parser dropped any call whose integer argument read `120.0`, so Coder-Next looked
  as if it announced a step and stopped; integer parameters are now sent as whole numbers (v0.6.1).
- An identical `todo_write` sent 98 times is now refused like other repeated calls (v0.6.1).
- Starting or stopping a background process resets the repeat count, so a client can be re-run after its server
  was started (v0.6.2).

## M4 Air (32 GB)

**Use only the 27B there, as the 4-bit build: `lmstudio-community/Qwen3.8-27B-MLX-4bit` on 8083.** Coder-Next
needs ~44 GB and does not fit; the 6-bit 27B peaks at ~27 GB and does not fit either. The 4-bit 27B passed 20 of
20 hard runs (peak ~21 GB) in the earlier 4-bit vs 6-bit comparison. Set it up with `docs/LOCAL_SETUP.md` (the
32 GB row) and do not install the Coder-Next model, alias or script on that machine.

## Reproducing

```
python -m evals.run_evals --set hard --repeat 2 --sandbox --model <model>
python -m evals.run_evals --real evals/real/mlx-toolkit.json --sandbox --timeout 1800 --model <model>
python -m evals.run_scenarios --model <model>            # 3 scenarios x seeds 1-3
python -m evals.compare_models --run 27B:hard:<stamp> --scenarios 27B:evals/results/scenarios-<time>
```

Run from the repo root with the aider-chat interpreter, one model server at a time.
