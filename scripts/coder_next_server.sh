#!/bin/sh
# Starts or stops Qwen3-Coder-Next (abliterated, MLX 4bit) on 8084 for `aider --model coder`, on a 64 GB Mac only.
# It needs ~44 GB, so start stops the 8080 (Heretic) and 8083 (27B) LaunchAgents first, and stop brings them back.
# The default agent model stays the 27B on 8083; see docs/MODEL_COMPARISON.md for why and for the 32 GB laptop.
MODEL_ID=veeceey/Huihui-Qwen3-Coder-Next-abliterated-mlx-4bit
PORT=8084
CACHE_BYTES=8589934592
PYTHON=$HOME/.venvs/mlx-vlm/bin/python
LOG=$HOME/.cache/mlx-coder-next.log
PID_FILE=$HOME/.cache/mlx-coder-next.pid
LA=$HOME/Library/LaunchAgents
DOMAIN=gui/$(id -u)
WAIT_STEPS=60
WAIT_SECONDS=5

listening() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1; }

wait_until() {  # $1 = up|down, $2 = port
  i=0
  while [ $i -lt $WAIT_STEPS ]; do
    if [ "$1" = up ] && [ -n "$(listening "$2")" ]; then return 0; fi
    if [ "$1" = down ] && [ -z "$(listening "$2")" ]; then return 0; fi
    sleep $WAIT_SECONDS; i=$((i + 1))
  done
  return 1
}

start() {
  if [ -n "$(listening $PORT)" ]; then echo "Coder-Next already running on $PORT"; return 0; fi
  launchctl bootout "$DOMAIN/local.mlx-serve" 2>/dev/null
  launchctl bootout "$DOMAIN/local.mlx-lm-agent" 2>/dev/null
  wait_until down 8080 && wait_until down 8083 || { echo "8080 or 8083 did not stop; not starting"; exit 1; }
  nohup "$PYTHON" -m mlx_lm server --model "$MODEL_ID" --host 127.0.0.1 --port $PORT \
    --prompt-cache-bytes $CACHE_BYTES > "$LOG" 2>&1 &
  echo $! > "$PID_FILE"
  wait_until up $PORT && echo "Coder-Next up on $PORT; use: aider-agent --model coder" || echo "not up yet; see $LOG"
}

stop() {
  [ -f "$PID_FILE" ] && kill "$(cat "$PID_FILE")" 2>/dev/null
  rm -f "$PID_FILE"
  wait_until down $PORT || echo "8084 still up; check $LOG"
  launchctl bootstrap "$DOMAIN" "$LA/local.mlx-serve.plist" 2>/dev/null
  launchctl bootstrap "$DOMAIN" "$LA/local.mlx-lm-agent.plist" 2>/dev/null
  wait_until up 8083 && echo "8083 (27B) back up" || echo "8083 not up yet"
}

case "$1" in
  start) start ;;
  stop) stop ;;
  status) for p in 8080 8083 $PORT; do pid=$(listening $p); echo "$p: ${pid:-down}"; done ;;
  *) echo "usage: $0 start|stop|status"; exit 2 ;;
esac
