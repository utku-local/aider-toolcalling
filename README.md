# aider-toolcalling

A patched copy of the [Aider](https://github.com/Aider-AI/aider) 0.86.2 `aider` package that adds OpenAI-compatible
native tool calling, aimed at a local MLX model served by `mlx_lm`. With `--native-tools` the model can call
read-only project tools; Aider executes them, sends the results back and the final answer goes through Aider's
normal edit pipeline.

## Status

Prototype. Only the `aider/` package is tracked; it runs on top of an installed `aider-chat` 0.86.2, which provides
all dependencies.

## Setup

1. Install Aider 0.86.2 as a uv tool (provides the interpreter and dependencies):

   ```
   uv tool install --python 3.12 aider-chat==0.86.2
   ```

2. Clone this repo, for example to `~/aider-toolcalling-dev`.
3. Point Aider at the local model server in `~/.aider.conf.yml` (`model: openai/<model-id>`,
   `openai-api-base: http://127.0.0.1:<port>/v1`).

## Usage

Run the patched package from any project directory:

```
PYTHONPATH=~/aider-toolcalling-dev ~/.local/share/uv/tools/aider-chat/bin/python -m aider --native-tools
```

`PYTHONPATH` is required: launching the `aider` command or running a script from elsewhere imports the unpatched
installed copy instead.

- `--native-tools` (default off) exposes `read_file` and `list_files`, both confined to the project root.
- It implies `--no-stream`; streaming tool calls are not supported yet.
- At most 8 model/tool round trips per message; after that the model is asked to answer without tools.
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
| `aider/native_tools_builtin.py` | Read-only `read_file` / `list_files` tools |
| `aider/coders/native_tool_rounds.py` | Drives the tool loop for a Coder |
| `aider/models.py`, `aider/coders/base_coder.py`, `aider/args.py`, `aider/main.py` | Small hooks into upstream Aider |
| `tests/` | Unit and mocked end-to-end tests |

## Tests

Run from the repo root so the patched package is imported:

```
~/.local/share/uv/tools/aider-chat/bin/python -m unittest discover -s tests
```

## License

Aider is licensed under the Apache License 2.0; see `LICENSE.txt`. The changes in this repo use the same license.
