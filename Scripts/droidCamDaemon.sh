#!/usr/bin/env bash
# droidCamDaemon.sh — auto-connect/disconnect DroidCam based on phone app reachability.
# Reads ip/port from ~/.config/droidcam; env overrides: HOST=, PORT=
set -euo pipefail

droidcamConf="${HOME}/.config/droidcam"
HOST="${HOST:-$(grep '^ip='   "$droidcamConf" 2>/dev/null | cut -d= -f2)}"
PORT="${PORT:-$(grep '^port=' "$droidcamConf" 2>/dev/null | cut -d= -f2)}"
HOST="${HOST:-192.168.0.156}"
PORT="${PORT:-4747}"

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}"
PIDFILE="$CACHE_DIR/droidcam-watch.pid"
LOCKFILE="$CACHE_DIR/droidcam-watch.lock"

cleanup() {
  [[ -n "${DC_PID:-}" ]] && kill "$DC_PID" 2>/dev/null || true
  pkill -x droidcam-cli 2>/dev/null || true
  rm -f "$PIDFILE" "$LOCKFILE" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# If an old supervisor is running, stop it (restart behavior)
if [[ -f "$PIDFILE" ]]; then
  oldPid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "${oldPid:-}" ]] && kill -0 "$oldPid" 2>/dev/null; then
    echo "[droidcam-watch] Restarting: stopping old supervisor pid $oldPid"
    pkill -P "$oldPid" 2>/dev/null || true
    kill "$oldPid" 2>/dev/null || true
    pkill -x droidcam-cli 2>/dev/null || true
    sleep 0.5
  fi
fi

# Single-instance lock
exec 9>"$LOCKFILE"
flock -n 9 || { echo "[droidcam-watch] Another instance is running. Exiting."; exit 1; }

echo $$ >"$PIDFILE"
echo "[droidcam-watch] Watching ${HOST}:${PORT}"

while :; do
  # Wait until phone app is listening
  until nc -z -w1 "$HOST" "$PORT" >/dev/null 2>&1; do sleep 2; done

  pkill -x droidcam-cli 2>/dev/null || true
  droidcam-cli -nocontrols -dev=/dev/video20 -size=1920x1080 "$HOST" "$PORT" &
  DC_PID=$!
  echo "[droidcam-watch] Connected (pid $DC_PID)"

  # Monitor: exit inner loop when phone unreachable or process died
  while kill -0 "$DC_PID" 2>/dev/null && nc -z -w1 "$HOST" "$PORT" >/dev/null 2>&1; do
    sleep 2
  done

  kill "$DC_PID" 2>/dev/null || true
  echo "[droidcam-watch] Disconnected; waiting for reconnect…"
  sleep 1
done
