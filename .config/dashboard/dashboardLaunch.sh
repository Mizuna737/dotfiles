#!/usr/bin/env bash
# dashboard-launch.sh
# Starts the Python bridge server and opens the dashboard in luakit
# on the secondary screen. Called from AwesomeWM autostart.

DASHBOARD_DIR="$HOME/.config/dashboard"
SERVER_SCRIPT="$DASHBOARD_DIR/dashboardServer.py"
LOG_FILE="$HOME/.cache/dashboard-server.log"
PID_FILE="$HOME/.cache/dashboard-server.pid"

# ── Start server (if not already running) ─────────────────────────────────
if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
  echo "Dashboard server already running."
else
  python3 "$SERVER_SCRIPT" >> "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  echo "Dashboard server started (PID $(cat $PID_FILE))."
  sleep 0.5
fi

# ── Launch luakit only if not already running ──────────────────────────────
if xdotool search --classname dashboard 2>/dev/null | grep -q .; then
  echo "Dashboard already running."
  exit 0
fi

WEBKIT_DISABLE_DMABUF_RENDERER=1 luakit \
  --class dashboard \
  "http://localhost:9876" &
