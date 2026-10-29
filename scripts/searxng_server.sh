#!/bin/sh
# Installs and runs a private SearXNG on 127.0.0.1:8888 so the agent's web_search has a search service.
# install clones SearXNG into ~/opt/searxng with its own venv and writes a localhost-only settings file with JSON
# output. start/stop run it in the background, and enable/disable make it a LaunchAgent that starts at login.
REPO_URL=https://github.com/searxng/searxng.git
SRC=$HOME/opt/searxng
VENV=$HOME/.venvs/searxng
PYTHON=$VENV/bin/python
PYTHON_VERSION=3.12
SETTINGS=$HOME/.config/searxng/settings.yml
PORT=8888
LOG=$HOME/.cache/searxng.log
PID_FILE=$HOME/.cache/searxng.pid
LABEL=local.searxng
PLIST=$HOME/Library/LaunchAgents/$LABEL.plist
DOMAIN=gui/$(id -u)
WAIT_STEPS=30
WAIT_SECONDS=1
SEARCH_URL="http://127.0.0.1:$PORT/search?q={query}&format=json"

listening() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | head -1; }

wait_up() {
  i=0
  while [ $i -lt $WAIT_STEPS ]; do
    curl -s -o /dev/null "http://127.0.0.1:$PORT/healthz" && return 0
    sleep $WAIT_SECONDS; i=$((i + 1))
  done
  return 1
}

write_settings() {
  [ -f "$SETTINGS" ] && return 0
  mkdir -p "$(dirname "$SETTINGS")"
  umask 077
  cat > "$SETTINGS" <<EOF
use_default_settings: true
server:
  secret_key: "$(openssl rand -hex 32)"
  bind_address: "127.0.0.1"
  port: $PORT
  limiter: false
  public_instance: false
  image_proxy: false
search:
  formats:
    - html
    - json
valkey:
  url: false
EOF
}

install() {
  [ -d "$SRC/.git" ] || git clone --depth 1 "$REPO_URL" "$SRC" || exit 1
  [ -x "$PYTHON" ] || uv venv --python $PYTHON_VERSION "$VENV" || exit 1
  uv pip install --python "$PYTHON" -r "$SRC/requirements.txt" -r "$SRC/requirements-server.txt" || exit 1
  write_settings
  echo "Installed. Next: $0 start, then export AIDER_AGENT_SEARCH_URL='$SEARCH_URL'"
}

start() {
  if [ -n "$(listening)" ]; then echo "SearXNG already running on $PORT"; return 0; fi
  (cd "$SRC" || exit 1; SEARXNG_SETTINGS_PATH="$SETTINGS" nohup "$PYTHON" -m searx.webapp > "$LOG" 2>&1 &
   echo $! > "$PID_FILE")
  wait_up && echo "SearXNG up: $SEARCH_URL" || echo "not up yet; see $LOG"
}

stop() {
  [ -f "$PID_FILE" ] && kill "$(cat "$PID_FILE")" 2>/dev/null
  rm -f "$PID_FILE"
}

enable() {
  stop
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PYTHON</string><string>-m</string><string>searx.webapp</string></array>
  <key>WorkingDirectory</key><string>$SRC</string>
  <key>EnvironmentVariables</key><dict><key>SEARXNG_SETTINGS_PATH</key><string>$SETTINGS</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
  launchctl bootstrap "$DOMAIN" "$PLIST" && wait_up && echo "SearXNG starts at login: $SEARCH_URL"
}

disable() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null
  rm -f "$PLIST"
}

case "$1" in
  install) install ;;
  start) start ;;
  stop) stop ;;
  enable) enable ;;
  disable) disable ;;
  status) pid=$(listening); echo "$PORT: ${pid:-down}" ;;
  *) echo "usage: $0 install|start|stop|enable|disable|status"; exit 2 ;;
esac
