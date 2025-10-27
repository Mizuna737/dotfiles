#!/bin/bash

LOCKFILE="/tmp/selectPhotosForSD.lock"

if [ -f "$LOCKFILE" ] && kill -0 "$(cat "$LOCKFILE")" 2>/dev/null; then
  echo "selectPhotosForSD is already running."
  exit 1
fi

echo $$ >"$LOCKFILE"
trap "rm -f '$LOCKFILE'" EXIT

# Source and destination base
SOURCE_DIR="/data/Photos"
DEST_BASE="/run/media"

echo "📸 Photo Selection Script"

# Prompt for destination
read -rp "Destination folder under /run/media (e.g. yourusername/SDCARD): " DEST_SUB
DEST="$DEST_BASE/$DEST_SUB"

if [ ! -d "$DEST" ]; then
  echo "❌ Destination folder does not exist: $DEST"
  exit 1
fi

echo "✅ Destination set to: $DEST"

# Find all images
echo "🔍 Finding images..."
mapfile -t IMAGES < <(find "$SOURCE_DIR" -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.gif' \) | sort -u)

if [[ ${#IMAGES[@]} -eq 0 ]]; then
  echo "❌ No images found in $SOURCE_DIR"
  exit 1
fi

echo "✅ Found ${#IMAGES[@]} images."

# Use nsxiv for visual multi-selection
echo "✅ Launching nsxiv for selection..."
mapfile -t SELECTED_IMAGES < <(nsxiv -ot "${IMAGES[@]}")

if [[ ${#SELECTED_IMAGES[@]} -eq 0 ]]; then
  echo "⚠️ No photos selected. Exiting."
  exit 0
fi

echo "✅ Selected ${#SELECTED_IMAGES[@]} images:"
for IMG in "${SELECTED_IMAGES[@]}"; do
  echo "  $IMG"
done

echo
read -rp "Proceed to copy these images to $DEST? (y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "❌ Copy cancelled."
  exit 1
fi

# Perform the copy with sudo (assuming /run/media is root-owned)
echo "✅ Copying..."
for IMG in "${SELECTED_IMAGES[@]}"; do
  sudo cp -v "$IMG" "$DEST"
done

echo "✅ All selected images copied to $DEST"
