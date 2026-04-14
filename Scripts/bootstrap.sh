#!/bin/bash
# bootstrap.sh — Fresh-machine setup from dotfiles clone.
# Installs paru, all explicitly-tracked packages, links dotfiles via stow,
# and installs the pacman hook that keeps packages/{native,aur}.txt up to date.
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGES_DIR="$DOTFILES_DIR/packages"

# ── Colors ────────────────────────────────────────────────────────────────────
BOLD='\033[1m'; RESET='\033[0m'
BLUE='\033[1;34m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; RED='\033[1;31m'

hdr()  { echo -e "\n${BLUE}::${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $*"; }
die()  { echo -e "  ${RED}✗${RESET} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] && die "Do not run as root. sudo will be invoked as needed."

# ── Step 1: base-devel (needed to build paru) ─────────────────────────────────
hdr "Installing base-devel..."
sudo pacman -S --needed --noconfirm base-devel git
ok "base-devel ready."

# ── Step 2: Install paru ──────────────────────────────────────────────────────
if command -v paru &>/dev/null; then
    ok "paru already installed — skipping."
else
    hdr "Building paru from AUR..."
    PARU_TMP=$(mktemp -d)
    trap 'rm -rf "$PARU_TMP"' EXIT
    git clone https://aur.archlinux.org/paru.git "$PARU_TMP/paru"
    (cd "$PARU_TMP/paru" && makepkg -si --noconfirm)
    trap - EXIT
    ok "paru installed."
fi

# ── Step 3: Native (repo) packages ───────────────────────────────────────────
hdr "Installing native packages..."
NATIVE_PKGS=()
while IFS= read -r pkg; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    NATIVE_PKGS+=("$pkg")
done < "$PACKAGES_DIR/native.txt"

# --needed skips already-installed packages; failures are soft-warned
FAILED_NATIVE=()
for pkg in "${NATIVE_PKGS[@]}"; do
    if ! sudo pacman -S --needed --noconfirm "$pkg" 2>/dev/null; then
        FAILED_NATIVE+=("$pkg")
        warn "Could not install: $pkg"
    fi
done
ok "Native packages done. (${#FAILED_NATIVE[@]} skipped)"

# ── Step 4: AUR packages ──────────────────────────────────────────────────────
hdr "Installing AUR packages..."
AUR_PKGS=()
while IFS= read -r pkg; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    AUR_PKGS+=("$pkg")
done < "$PACKAGES_DIR/aur.txt"

FAILED_AUR=()
for pkg in "${AUR_PKGS[@]}"; do
    if ! paru -S --needed --noconfirm "$pkg" 2>/dev/null; then
        FAILED_AUR+=("$pkg")
        warn "Could not install: $pkg"
    fi
done
ok "AUR packages done. (${#FAILED_AUR[@]} skipped)"

# ── Step 5: Stow dotfiles ─────────────────────────────────────────────────────
hdr "Stowing dotfiles..."
cd "$DOTFILES_DIR"

# Determine which top-level dirs/files stow should manage
# (exclude repo meta-files and non-stow dirs)
STOW_TARGETS=()
for entry in .config Documents Scripts .screenlayout .zshrc .zprofile .xprofile .xinitrc; do
    [[ -e "$DOTFILES_DIR/$entry" ]] && STOW_TARGETS+=("$entry")
done

stow --target="$HOME" --restow "${STOW_TARGETS[@]}"
ok "Dotfiles linked."

# ── Step 6: Install pacman hook ───────────────────────────────────────────────
hdr "Installing pacman hook..."
sudo install -Dm644 \
    "$DOTFILES_DIR/hooks/99-update-pkglist.hook" \
    /etc/pacman.d/hooks/99-update-pkglist.hook
sudo chmod +x "$DOTFILES_DIR/Scripts/updatePkgList.sh"
ok "Hook installed — packages/{native,aur}.txt will auto-update on install/remove."

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Bootstrap complete.${RESET}"
if [[ ${#FAILED_NATIVE[@]} -gt 0 || ${#FAILED_AUR[@]} -gt 0 ]]; then
    warn "Some packages were skipped (may be hardware-specific or renamed):"
    for p in "${FAILED_NATIVE[@]}" "${FAILED_AUR[@]}"; do
        echo "    - $p"
    done
fi
echo ""
echo "  Next steps:"
echo "    • Enable services:  systemctl enable --now NetworkManager bluetooth tailscaled"
echo "    • Set up shell:     chsh -s /usr/bin/zsh"
echo "    • Check hardware:   nvidia-smi / lspci for GPU driver needs"
