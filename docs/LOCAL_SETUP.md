# Setting up a Mac from scratch

This is the exact setup the project is developed and measured on, written so a second Mac (for example a 32 GB
laptop) can be brought to the same state. Every file it installs has a template in `docs/examples/`.

## What you end up with

| Port | Server | Model | Starts | Used by |
|---|---|---|---|---|
| 8083 | `mlx_lm.server` | your text model (see "Choose the model") | at login | `aider` and `aider-agent` |
| 8081 | `mlx_vlm.server` | same model, optional | by hand | anything that needs image input |

`mlx_lm.server` reuses its prompt cache when a request extends the previous one, which is what every agent round
does; `mlx_vlm.server` does not. Measured on the same 27B model, a real agent task took 237 s on `mlx_lm` and
1,060 s on `mlx_vlm`. `mlx_vlm` is only needed for images.

Both servers load their model **when they start**, not on the first request, and keep it in memory. Check real
usage with `footprint -p <pid>` (RSS does not show GPU memory).

## Choose the model

| Mac | Model for 8083 | Size | Prompt cache cap (`CACHE_BYTES`) |
|---|---|---|---|
| 64 GB | `ailexleon/Huihui-Qwen3.8-27B-abliterated-mlx-6Bit` | 21 GB on disk, up to ~27 GB in memory | 8589934592 (8 GB) |
| 32 GB | `lmstudio-community/Qwen3.8-27B-MLX-4bit` | 15 GB on disk, up to ~21 GB in memory | 4294967296 (4 GB) |

`mlx_lm.server` keeps a prompt cache next to the model; without a byte cap it was measured at 14 GB after one
evaluation run, so always set one.

Run at most one 27B server at a time on a 32 GB Mac, and do not start the optional 8081 server while 8083 is up.

Measured on the hard evaluation set (10 tasks, 2 runs each, both served by `mlx_lm`): 6-bit and 4-bit both
passed 20 of 20. Peak server memory was ~27 GB for 6-bit and ~21 GB for 4-bit, so 6-bit does not fit a 32 GB Mac.
Time outside prompt processing was the same (776 s and 763 s); the 4-bit total was longer only because that freshly
started server re-processed ~2,900 prompt tokens at the start of every task.

## 1. Tools

```
brew install uv gh
gh auth login            # the account that can read UttyWotty/aider-toolcalling
gh auth setup-git        # lets uv clone the private repository
```

## 2. Model server environment

```
uv venv --python 3.10 ~/.venvs/mlx-vlm
uv pip install --python ~/.venvs/mlx-vlm/bin/python mlx==0.32.0 mlx-vlm==0.6.10 mlx-lm==0.31.3
~/.venvs/mlx-vlm/bin/hf download <model id>      # optional; the server also downloads on first start
```

Always pass `--python` to `uv pip install`: without it uv installs into whatever Python comes first on `PATH`.

## 3. Start the 8083 server at login

```
MODEL=<model id from the table>
CACHE_BYTES=<cache cap from the table>
mkdir -p ~/.cache
sed -e "s|__HOME__|$HOME|g" -e "s|__MODEL__|$MODEL|g" -e "s|__CACHE_BYTES__|$CACHE_BYTES|g" \
    docs/examples/launchagents/local.mlx-lm-agent.plist > ~/Library/LaunchAgents/local.mlx-lm-agent.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.mlx-lm-agent.plist
curl -s http://127.0.0.1:8083/v1/models | head -c 200     # answers once the server is up
```

Optional image server on 8081 (by hand only):

```
sed -e "s|__HOME__|$HOME|g" -e "s|__MODEL__|$MODEL|g" \
    docs/examples/launchagents/local.mlx-serve-vlm.plist > ~/Library/LaunchAgents/local.mlx-serve-vlm.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.mlx-serve-vlm.plist     # loads, does not start
launchctl kickstart gui/$(id -u)/local.mlx-serve-vlm                                  # start
launchctl kill TERM gui/$(id -u)/local.mlx-serve-vlm                                  # stop
```

## 4. Aider configuration

```
cp docs/examples/aider.model.settings.yml ~/.aider.model.settings.yml
cp docs/examples/aider.model.metadata.json ~/.aider.model.metadata.json
sed -e "s|__MODEL_ID__|openai/$MODEL|" docs/examples/aider.conf.yml > ~/.aider.conf.yml
```

Back up existing files first if you have them. The settings point both Qwen3.8 27B variants at 8083, so
`aider --model 4bit` or `--model 6bit` only changes which model the 8083 server loads.

## 5. Install aider-agent

```
uv tool install --python 3.12 git+https://github.com/UttyWotty/aider-toolcalling.git@main
which -a aider-agent      # ~/.local/bin/aider-agent must be the first entry
```

`aider-agent` does not replace a separately installed `aider` command. To update later, run the same command with
`--force`.

## 6. Check it works

```
mkdir -p /tmp/agent-check && cd /tmp/agent-check
printf 'def greet(name):\n    return "Hello " + name\n' > greet.py
aider-agent --no-git --yes-always --message "Make greet return 'Hello, <name>!'"
cat greet.py              # return "Hello, " + name + "!"
grep -c "POST /v1/chat" ~/.cache/mlx-lm-agent.log      # grows with every agent run
```

## 7. Per-project settings (optional)

Copy `docs/examples/aider-agent.json` to a project as `.aider-agent.json` to run commands in the macOS sandbox and
let `pytest`, `unittest`, `git status` and `git diff` run without asking. `AGENTS.md` or `CLAUDE.md` in a project
root is added to agent sessions as read-only instructions.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Agent rounds take minutes | `aider` points at an `mlx_vlm` server; check `openai-api-base` and `api_base` are 8083 |
| `aider-agent` behaves like an old version | another `aider-agent` earlier on `PATH`; check `which -a aider-agent` |
| Heavy swap, everything slow | more than one model server loaded; check `footprint -p` per server and stop the extra one |
| A stopped server comes back | its plist has `KeepAlive`; the 8081 template has none, so a stop sticks |
