#!/bin/sh

run() {
  if ! pgrep -f "$*"; then
    "$@" &
  fi
}

# Use bash explicitly for pywal + wallpaper script
run bash "$HOME/Scripts/chooseWallpaper.sh" true
