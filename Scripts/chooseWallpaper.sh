#!/bin/bash

LOCKFILE="/tmp/chooseWallpaper.lock"

if [ -f "$LOCKFILE" ] && kill -0 "$(cat "$LOCKFILE")" 2>/dev/null; then
  echo "chooseWallpaper is already running."
  exit 1
fi

echo $$ >"$LOCKFILE"

trap "rm -f '$LOCKFILE'" EXIT

WALLPAPER_DIR=~/wallpapers

# Find unique images (ignores duplicate basenames)
mapfile -t IMAGES < <(find "$WALLPAPER_DIR" -type f \( -iname '*.jpg' -o -iname '*.png' -o -iname '*.jpeg' \) | sort -u)

# Exit if no images found
if [[ ${#IMAGES[@]} -eq 0 ]]; then
  echo "No wallpapers found in $WALLPAPER_DIR"
  exit 1
fi

# Determine selection mode
if [[ "$1" == "true" ]]; then
  SELECTED_IMAGE="${IMAGES[RANDOM % ${#IMAGES[@]}]}"
else
  SELECTED_IMAGE=$(nsxiv -ot "${IMAGES[@]}" | head -n 1)
fi

# Exit if no image was selected
if [[ -z "$SELECTED_IMAGE" ]]; then
  echo "No wallpaper selected."
  exit 1
fi

# Set wallpaper and color scheme with pywal
wal -i "$SELECTED_IMAGE" --backend colorz --saturate 0.3
echo "$SELECTED_IMAGE" >"$HOME/.cache/last-wallpaper"
echo "Wallpaper set to: $SELECTED_IMAGE"

# Apply theme updates across the system
bash "$HOME/Scripts/exportWalVars.sh"
bash "$HOME/Scripts/updateRofiColors.sh"
bash "$HOME/Scripts/updateTMUXColors.sh"
bash "$HOME/Scripts/updateObsidianColors.sh"
bash "$HOME/Scripts/updateZenTheme.sh"
tmux source-file "$HOME/.config/tmux/tmux.conf"
awesome-client "awesome.emit_signal('save::focused_tag')"
awesome-client "awesome.restart()"
