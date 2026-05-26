#!/usr/bin/env bash
# Symlink Vieb erwic .desktop files + icons into the right XDG dirs
# so rofi (and any DE launcher) picks them up.
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
appDir="$HOME/.local/share/applications"
iconDir="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$appDir" "$iconDir" "$HOME/.config/Vieb"

# Make erwic JSONs reachable at $HOME/.config/Vieb/erwics so .desktop Exec
# paths resolve regardless of whether the rest of Vieb is stowed.
ln -snf "$src" "$HOME/.config/Vieb/erwics"
echo "linked $HOME/.config/Vieb/erwics -> $src"

for f in "$src"/desktop/*.desktop; do
  ln -snf "$f" "$appDir/$(basename "$f")"
  echo "linked $appDir/$(basename "$f")"
done

for f in "$src"/icons/*.svg; do
  ln -snf "$f" "$iconDir/$(basename "$f")"
  echo "linked $iconDir/$(basename "$f")"
done

# Refresh icon + desktop caches if the tools are present
command -v gtk-update-icon-cache >/dev/null && \
  gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null && \
  update-desktop-database -q "$appDir" 2>/dev/null || true

echo "done."
