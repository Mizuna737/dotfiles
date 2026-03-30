#!/usr/bin/env zsh
# dpmsInhibit.sh — Disable DPMS/screensaver while media is playing via playerctl.
# Polls playerctl status every 30s; disables DPMS on Play, restores on Pause/Stop.

POLL_INTERVAL=30
dpmsEnabled=true

# Set to false to silence notifications once confirmed working
DEBUG_NOTIFY=false

notify() {
  if [[ "$DEBUG_NOTIFY" == true ]]; then
    notify-send -a "dpmsInhibit" -t 4000 "$1" "$2"
  fi
}

setDpms() {
  local state="$1"
  if [[ "$state" == "off" ]]; then
    xset s off
    xset -dpms
    dpmsEnabled=false
    notify "DPMS Disabled" "Media is playing — screen sleep suppressed."
  else
    xset s on
    xset +dpms
    dpmsEnabled=true
    notify "DPMS Restored" "Media stopped — screen sleep re-enabled."
  fi
}

notify "dpmsInhibit Started" "Polling every ${POLL_INTERVAL}s. DPMS currently enabled."

while true; do
  playerStatus="$(playerctl status 2>/dev/null || echo "Stopped")"

  if [[ "$playerStatus" == "Playing" ]]; then
    if $dpmsEnabled; then
      setDpms off
    else
      notify "Poll" "Status: Playing — DPMS already off, resetting idle timer."
    fi
    xset s reset
  else
    if ! $dpmsEnabled; then
      setDpms on
    else
      notify "Poll" "Status: ${playerStatus} — DPMS already on, nothing to do."
    fi
  fi

  sleep "$POLL_INTERVAL"
done
