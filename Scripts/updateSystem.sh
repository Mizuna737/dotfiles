#!/bin/bash
# updateSystem.sh — Snapshot current system, then run paru -Syu
set -euo pipefail

MAX_SNAPSHOTS=5
SNAP_PREFIX="pre-update"
BTRFS_DEV=$(findmnt -n -o SOURCE / | sed 's/\[.*\]//')
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
SNAP_NAME="${SNAP_PREFIX}_${TIMESTAMP}"

# 1. Sync current /boot into btrfs so the snapshot captures it
echo ":: Syncing /boot → /.bootbackup..."
sudo rsync -a --delete /boot/ /.bootbackup/

# 2. Mount top-level btrfs volume
MNTDIR=$(mktemp -d)
sudo mount -o subvolid=5 "$BTRFS_DEV" "$MNTDIR"
trap 'sudo umount "$MNTDIR" 2>/dev/null; rmdir "$MNTDIR" 2>/dev/null' EXIT

# 3. Ensure snapshots directory exists
sudo mkdir -p "${MNTDIR}/@snapshots"

# 4. Enforce retention — remove oldest snapshots first
mapfile -t EXISTING < <(find "${MNTDIR}/@snapshots" -maxdepth 1 -name "${SNAP_PREFIX}_*" -type d | sort)
COUNT=${#EXISTING[@]}

while [ "$COUNT" -ge "$MAX_SNAPSHOTS" ]; do
    OLDEST="${EXISTING[0]}"
    echo ":: Removing old snapshot: $(basename "$OLDEST")..."
    sudo btrfs subvolume delete "$OLDEST" > /dev/null
    EXISTING=("${EXISTING[@]:1}")
    COUNT=$((COUNT - 1))
done

# 5. Create snapshot of current @ subvolume
echo ":: Creating snapshot: ${SNAP_NAME}..."
sudo btrfs subvolume snapshot "${MNTDIR}/@" "${MNTDIR}/@snapshots/${SNAP_NAME}" > /dev/null
echo "   Snapshot created successfully."

# 6. Unmount top-level (trigger trap cleanup)
sudo umount "$MNTDIR"
rmdir "$MNTDIR"
trap - EXIT

# 7. Regenerate GRUB to include the new snapshot
echo ":: Regenerating GRUB config..."
sudo grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | grep -E "^(Found|done|Generating)"

# 8. Run the actual system update
echo ""
echo ":: Running system update..."
paru -Syu

# 9. Regenerate GRUB again in case the kernel changed
echo ""
echo ":: Regenerating GRUB config (post-update)..."
sudo grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | grep -E "^(Found|done|Generating)"

echo ""
echo ":: Update complete. ${SNAP_NAME} is bootable from GRUB."
