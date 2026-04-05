#!/bin/bash
# rollbackSystem.sh — Promote the currently booted snapshot to main @
#
# Usage: boot into a snapshot from GRUB, then run this script.
# It replaces @ with the snapshot you're running, restores /boot, and reboots.
set -euo pipefail

BTRFS_DEV=$(findmnt -n -o SOURCE / | sed 's/\[.*\]//')
CURRENT_SUBVOL=$(findmnt -n -o SOURCE / | grep -oP '\[\K[^]]+' | sed 's|^/||')

if [ "$CURRENT_SUBVOL" = "@" ]; then
    echo "You're booted from the main @ subvolume, not a snapshot."
    echo "Boot into a snapshot from GRUB first, then run this script."
    exit 1
fi

echo "Currently booted from: ${CURRENT_SUBVOL}"
echo ""
echo "This will:"
echo "  1. Rename current @ → @broken"
echo "  2. Snapshot ${CURRENT_SUBVOL} → @"
echo "  3. Restore /boot from the snapshot's /.bootbackup"
echo "  4. Regenerate GRUB and reboot"
echo ""
read -p "Proceed? [y/N] " confirm
if [ "$confirm" != "y" ]; then
    echo "Aborted."
    exit 0
fi

MNTDIR=$(mktemp -d)
sudo mount -o subvolid=5 "$BTRFS_DEV" "$MNTDIR"
trap 'sudo umount "$MNTDIR" 2>/dev/null; rmdir "$MNTDIR" 2>/dev/null' EXIT

# Remove any previous @broken
if [ -d "${MNTDIR}/@broken" ]; then
    echo ":: Removing previous @broken..."
    sudo btrfs subvolume delete "${MNTDIR}/@broken" > /dev/null
fi

# Move broken @ out of the way
echo ":: Moving @ → @broken..."
sudo mv "${MNTDIR}/@" "${MNTDIR}/@broken"

# Create writable snapshot of the good snapshot as the new @
echo ":: Creating new @ from ${CURRENT_SUBVOL}..."
sudo btrfs subvolume snapshot "${MNTDIR}/${CURRENT_SUBVOL}" "${MNTDIR}/@" > /dev/null

# Restore /boot from the snapshot's bootbackup
echo ":: Restoring /boot from /.bootbackup..."
sudo rsync -a --delete "${MNTDIR}/@/.bootbackup/" /boot/

# Cleanup
sudo umount "$MNTDIR"
rmdir "$MNTDIR"
trap - EXIT

# Regenerate GRUB
echo ":: Regenerating GRUB..."
sudo grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | grep -E "^(Found|done|Generating)"

echo ""
echo ":: Rollback complete. The broken @ is preserved as @broken."
echo "   Run 'sudo btrfs subvolume delete /path/to/@broken' to reclaim space once satisfied."
echo ""
read -p "Reboot now? [y/N] " reboot_confirm
if [ "$reboot_confirm" = "y" ]; then
    sudo reboot
fi
