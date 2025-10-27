#!/usr/bin/env bash
# virtualCamMux.sh — Always-on VirtualCam: black when idle, DroidCam when active.
# Debug echos included. Optional live preview.
#
# Env/args:
#   SRC=/dev/video2   SINK=/dev/video10   SIZE=1280x720   FPS=10
#   VIEW=1            # launch a viewer for SINK
#   LOG=/path/file    # collect ffmpeg logs (default /dev/null)

command -v ffprobe >/dev/null || {
  echo "[mux] ERROR: ffprobe not found (pacman -S ffmpeg)"
  exit 1
}
set -euo pipefail

SRC=${SRC:-/dev/video2}
SINK=${SINK:-/dev/video10}
SIZE=${SIZE:-1280x720}
FPS=${FPS:-10}
LOG=${LOG:-/dev/null}
VIEW=${VIEW:-0}

echo "[mux] SRC=$SRC  SINK=$SINK  SIZE=$SIZE  FPS=$FPS  VIEW=$VIEW"
command -v v4l2-ctl >/dev/null || {
  echo "[mux] ERROR: v4l2-ctl not found (pacman -S v4l-utils)"
  exit 1
}
command -v ffmpeg >/dev/null || {
  echo "[mux] ERROR: ffmpeg not found (pacman -S ffmpeg)"
  exit 1
}

# Launch a viewer on SINK (non-blocking) if requested
launch_viewer() {
  if [[ "$VIEW" = "1" ]]; then
    if pgrep -f "mpv .*${SINK}" >/dev/null 2>&1 || pgrep -f "ffplay .*${SINK}" >/dev/null 2>&1; then
      echo "[mux] Viewer already running, not launching another."
      return
    fi
    if command -v mpv >/dev/null 2>&1; then
      echo "[mux] Launching viewer (mpv) for $SINK ..."
      nohup mpv --no-audio --profile=low-latency --untimed "$SINK" \
        >/dev/null 2>&1 &
    elif command -v ffplay >/dev/null 2>&1; then
      echo "[mux] Launching viewer (ffplay) for $SINK ..."
      nohup ffplay -hide_banner -loglevel error -fflags nobuffer -flags low_delay \
        -f v4l2 -framerate "$FPS" -video_size "$SIZE" -i "$SINK" \
        >/dev/null 2>&1 &
    else
      echo "[mux] NOTE: No mpv/ffplay found; skipping viewer."
    fi
  fi
}

run_relay() {
  echo "[mux] Relay: $SRC -> $SINK (auto-detect format)..."
  # 1) Try auto-detect (no -input_format)
  ffmpeg -loglevel error -re -f v4l2 -i "$SRC" -f v4l2 -pix_fmt yuv420p "$SINK" >>"$LOG" 2>&1 && return
  echo "[mux] Auto-detect failed, trying mjpeg…"
  # 2) Try mjpeg
  ffmpeg -loglevel error -re -f v4l2 -input_format mjpeg -i "$SRC" -f v4l2 -pix_fmt yuv420p "$SINK" >>"$LOG" 2>&1 && return
  echo "[mux] MJPEG failed, trying yuyv422…"
  # 3) Try yuyv422
  ffmpeg -loglevel error -re -f v4l2 -input_format yuyv422 -i "$SRC" -f v4l2 -pix_fmt yuv420p "$SINK" >>"$LOG" 2>&1 || true
  echo "[mux] Relay pipeline ended (source stopped or unsupported format)."
}

is_src_capture_ready() {
  # Device exists & is readable (don’t rely on caps text)
  [[ -e "$SRC" ]] || return 1
  # Quick, non-blocking probe (2 frames max); success exit means readable stream
  ffprobe -v error -f v4l2 -i "$SRC" -count_frames -read_intervals %+#0.1 -select_streams v:0 >/dev/null 2>&1
}

run_black() {
  echo "[mux] Fallback: black -> $SINK ..."
  ffmpeg -loglevel error -re \
    -f lavfi -i "color=size=${SIZE}:rate=${FPS}:color=black" \
    -f v4l2 -pix_fmt yuv420p "$SINK" >>"$LOG" 2>&1 || true
  echo "[mux] Black pipeline ended (will re-evaluate source)."
}

# Kick off viewer if requested
launch_viewer

echo "[mux] Entering main loop. Ctrl+C to stop."
while :; do
  if is_src_capture_ready; then
    echo "[mux] Source looks ready (Video Capture present)."
    run_relay
  else
    echo "[mux] Source not ready; feeding black."
    run_black
  fi
  sleep 0.3
done
