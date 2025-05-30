#!/usr/bin/env bash

set -euo pipefail

# 1. Pre-update snapshot
desc="pre-update $(date '+%Y-%m-%d %H:%M:%S')"
echo "📸 Creating snapshot: $desc"
sudo snapper create --description "$desc"

# 2. Update GRUB menu to include the snapshot
echo "🔄 Updating GRUB snapshot list..."
sudo /etc/grub.d/41_snapshots-btrfs >/dev/null
sudo grub-mkconfig -o /boot/grub/grub.cfg

# 3. Run pacman with minimal output
echo "📦 Updating system packages with pacman..."
sudo pacman -Syu --noconfirm | grep -E '^\s+\S+\s+\S+\s+->\s+\S+' || echo "(no updates)"

# 4. Run paru with minimal output
echo "📦 Updating AUR packages with paru..."
paru -Syu --noconfirm | grep -E '^\s+\S+\s+\S+\s+->\s+\S+' || echo "(no AUR updates)"

# 5. Prompt for reboot
echo ""
read -rp "✅ Updates complete. Reboot now? [y/N] " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
  echo "🔁 Rebooting..."
  reboot
else
  echo "❌ Reboot canceled. Don't forget to test and optionally create a post-update snapshot."
fi
