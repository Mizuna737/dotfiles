#!/usr/bin/env bash
# dashboard-launch.sh
# Starts the Python bridge server and opens the dashboard in qutebrowser
# on the secondary screen. Called from AwesomeWM autostart.

DASHBOARD_DIR="$HOME/.config/dashboard"
SERVER_SCRIPT="$DASHBOARD_DIR/dashboardServer.py"
HTML_FILE="$DASHBOARD_DIR/index.html"
LOG_FILE="$HOME/.cache/dashboard-server.log"
PID_FILE="$HOME/.cache/dashboard-server.pid"

# ── Always restart the server ──────────────────────────────────────────────
if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
  echo "Restarting dashboard server..."
  kill "$(cat $PID_FILE)"
  sleep 0.3
fi

python3 "$SERVER_SCRIPT" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Dashboard server started (PID $(cat $PID_FILE))."
sleep 0.5

# ── Launch qutebrowser only if not already running ─────────────────────────
if xdotool search --classname dashboard 2>/dev/null | grep -q .; then
  echo "Dashboard window already running."
  exit 0
fi

# --qt-arg name sets WM_CLASS instance so the window can be identified as "dashboard"
# content.local_content_can_access_remote_urls → allows file:// pages to
# fetch localhost (needed for the dashboard API bridge)
qutebrowser \
  --target window \
  --basedir "$HOME/.local/share/qutebrowser-dashboard" \
  --set tabs.show never \
  --set scrolling.bar never \
  --set statusbar.show never \
  --set content.local_content_can_access_remote_urls true \
  --qt-arg name dashboard \
  "file://$HTML_FILE" &
