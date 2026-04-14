#!/bin/bash
# updatePkgList.sh — Regenerate packages/{native,aur}.txt from current explicit installs.
# Called by the pacman hook after any install/remove transaction.
# Runs as root; writes to the dotfiles repo owned by max.

PACKAGES_DIR="/home/max/dotfiles/packages"

pacman -Qen | awk '{print $1}' | sort > "$PACKAGES_DIR/native.txt"
pacman -Qem | awk '{print $1}' | sort > "$PACKAGES_DIR/aur.txt"
