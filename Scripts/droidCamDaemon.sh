#!/usr/bin/env bash
# droidCamDaemon.sh — auto-connect/disconnect DroidCam based on phone app reachability.
# Reads ip/port from ~/.config/droidcam; env overrides: HOST=, PORT=
# Subnet scan added: if configured IP fails, scans the /24 for the phone.
set -euo pipefail

droidcamConf="${HOME}/.config/droidcam"
CONF_IP="${HOST:-$(grep '^ip='   "$droidcamConf" 2>/dev/null | cut -d= -f2)}"
PORT="${PORT:-$(grep '^port=' "$droidcamConf" 2>/dev/null | cut -d= -f2)}"
CONF_IP="${CONF_IP:-}"
PORT="${PORT:-4747}"

SCAN_LIB="$(dirname "$0")/lib/droidcamScan.py"

# findReachableHost IP PORT — scan /24 or try config IP, return (host port) via global vars.
# Uses droidcamScan.py when available, falls back to pure-bash nc scan.
SCAN_RESULT_HOST=""
SCAN_RESULT_PORT=""

_scanWithPython() {
  local ip="$1" port="$2"
  local scanDir
  SCAN_LIB="$(dirname "$0")/lib/droidcamScan.py"
  # Try relative path first, then fallback
  if [[ ! -f "$SCAN_LIB" ]]; then
    SCAN_LIB="${HOME}/Scripts/lib/droidcamScan.py"
  fi
  local result
  result=$(python3 -c "
import sys; sys.path.insert(0, '$(dirname "$SCAN_LIB")')
from droidcamScan import find_droidcam
h, p = find_droidcam('$ip', $port)
print(f'{h} {p}')
" 2>/dev/null) || return 1
  SCAN_RESULT_HOST="${result%% *}"
  SCAN_RESULT_PORT="${result##* }"
}

_scanBash() {
  local ip="$1" port="$2"
  local prefix="${ip%.*}"
  SCAN_RESULT_HOST=""
  SCAN_RESULT_PORT="$port"

  # Try config IP first (fast path)
  if nc -z -w1 "$ip" "$port" >/dev/null 2>&1; then
    SCAN_RESULT_HOST="$ip"
    return 0
  fi

  # Scan subnet
  local i
  for i in $(seq 1 254); do
    local host="${prefix%.*}.$i"
    if nc -z -w1 "$host" "$port" >/dev/null 2>&1; then
      SCAN_RESULT_HOST="$host"
      return 0
    fi
  done
  return 1
}

_findReachable() {
  local ip="$1" port="$2"
  if [[ -f "$SCAN_LIB" || -f "${HOME}/Scripts/lib/droidcamScan.py" ]]; then
    _scanWithPython "$ip" "$port" && return 0
  fi
  _scanBash "$ip" "$port"
}

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

_resolveHost() {
  local ip="$1" port="$2"
  SCAN_RESULT_HOST=""
  SCAN_RESULT_PORT=""
  if _findReachable "$ip" "$port"; then
    HOST="$SCAN_RESULT_HOST"
    PORT="$SCAN_RESULT_PORT"
    echo "[droidcam-watch] Found phone at ${HOST}:${PORT}"
    return 0
  else
    echo "[droidcam-watch] No phone found on subnet; using config IP $ip:$port"
    HOST="$ip"
    PORT="$port"
    return 1
  fi
}

# Initial resolve
if [[ -z "$CONF_IP" ]]; then
  echo "[droidcam-watch] No IP in config; scanning subnet…"
  _resolveHost "192.168.0.1" "$PORT" || true
else
  if ! _resolveHost "$CONF_IP" "$PORT"; then
    echo "[droidcam-watch] Config IP unreachable, trying subnet scan…"
    _resolveHost "$CONF_IP" "$PORT" || true
  fi
fi

echo "[droidcam-watch] Watching ${HOST}:${PORT}"

while :; do
  # Wait until phone app is listening (with periodic re-resolution)
  localRescanInterval=60
  localElapsed=0

  until nc -z -w1 "$HOST" "$PORT" >/dev/null 2>&1; do
    sleep 2
    localElapsed=$((localElapsed + 2))
    # Periodically re-scan the subnet in case phone changed IPs
    if [[ $localElapsed -ge $localRescanInterval ]]; then
      echo "[droidcam-watch] No response; re-scanning subnet…"
      localElapsed=0
      if _resolveHost "$HOST" "$PORT"; then
        continue
      fi
    fi
  done

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
