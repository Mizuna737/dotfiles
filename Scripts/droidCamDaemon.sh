#!/usr/bin/env bash
# droidcam-watch.sh — auto-reconnect DroidCam; single-instance; safe restart.
# Env overrides: HOST=192.168.0.156 PORT=4747 VIDEO_DEV=/dev/video2
set -euo pipefail

HOST="${HOST:-192.168.0.156}"
PORT="${PORT:-4747}"
VIDEO_DEV="${VIDEO_DEV:-/dev/video2}"

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$CACHE_DIR"
PIDFILE="$CACHE_DIR/droidcam-watch.pid"
LOCKFILE="$CACHE_DIR/droidcam-watch.lock"

cleanup() {
  local dc_pids
  [[ -n "${DC_PID:-}" ]] && kill "$DC_PID" 2>/dev/null || true
  # ensure no stray droidcam-cli (only one allowed)
  dc_pids="$(pgrep -x droidcam-cli || true)"
  [[ -n "$dc_pids" ]] && pkill -x droidcam-cli || true
  rm -f "$PIDFILE" "$LOCKFILE" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# If an old supervisor is running, stop it (restart behavior)
if [[ -f "$PIDFILE" ]]; then
  old_pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[droidcam-watch] Restarting: stopping old supervisor pid $old_pid"
    # Kill its child droidcam-cli and the supervisor
    pkill -P "$old_pid" 2>/dev/null || true
    kill "$old_pid" 2>/dev/null || true
    # Also ensure no stale droidcam-cli remains
    pkill -x droidcam-cli 2>/dev/null || true
    sleep 0.5
  fi
fi

# Single-instance lock (best-effort)
exec 9>"$LOCKFILE"
flock -n 9 || {
  echo "[droidcam-watch] Another instance is running. Exiting."
  exit 1
}

echo $$ >"$PIDFILE"

echo "[droidcam-watch] Watching ${HOST}:${PORT} → will run: droidcam-cli ${HOST} ${PORT}"

while :; do
  # Wait until phone app is listening
  until nc -z "$HOST" "$PORT" >/dev/null 2>&1; do sleep 1; done

  # Ensure only one droidcam-cli is active
  pgrep -x droidcam-cli >/dev/null && pkill -x droidcam-cli || true
  droidcam-cli -size=3840x2160 "$HOST" "$PORT" &
  DC_PID=$!
  echo "[droidcam-watch] Started droidcam-cli pid $DC_PID"

  # Stay up while the phone is reachable and the process is alive
  while nc -z "$HOST" "$PORT" >/dev/null 2>&1 && kill -0 "$DC_PID" 2>/dev/null; do
    sleep 2
  done

  # Clean up device if CLI died or phone app closed
  kill "$DC_PID" 2>/dev/null || true
  fuser -k "$VIDEO_DEV" 2>/dev/null || true
  echo "[droidcam-watch] Disconnected; retrying…"
  sleep 1
done
