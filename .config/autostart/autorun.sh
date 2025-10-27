#!/bin/sh

run() {
  if ! pgrep -f "$*"; then
    "$@" &
  fi
}

# If last wallpaper exists, reapply it with wal
if [ -f "$HOME/.cache/last-wallpaper" ]; then
  wal -R
fi
