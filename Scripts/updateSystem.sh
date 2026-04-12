#!/bin/bash
# updateSystem.sh — Snapshot current system, then update with single approval + progress bar
set -euo pipefail

# ── Colors ─────────────────────────────────────────────────────────────────────
BOLD='\033[1m'; RESET='\033[0m'
BLUE='\033[1;34m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; CYAN='\033[1;36m'

hdr()  { echo -e "${BLUE}::${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo -e "${GREEN}  ✓${RESET} $*"; }

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_SNAPSHOTS=5
SNAP_PREFIX="pre-update"
BTRFS_DEV=$(findmnt -n -o SOURCE / | sed 's/\[.*\]//')
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
SNAP_NAME="${SNAP_PREFIX}_${TIMESTAMP}"

# ── Reboot analysis ───────────────────────────────────────────────────────────
# Call after the update completes. Inspects the running system vs what was
# installed and prints a clear reboot/restart/nothing recommendation.
checkReboot() {
    local reasons=()
    local restarts=()

    # 1. Kernel version mismatch — uname -r vs installed kernel package(s)
    for kpkg in linux linux-lts linux-zen linux-hardened linux-rt linux-rt-lts; do
        if pacman -Q "$kpkg" &>/dev/null; then
            # Package version:  "6.14.1.arch1-1"  → uname format: "6.14.1-arch1-1"
            local pkgver
            pkgver=$(pacman -Q "$kpkg" | awk '{print $2}' | sed 's/\.arch/-arch/')
            local running
            running=$(uname -r)
            if [[ "$pkgver" != "$running" ]]; then
                reasons+=("kernel ($kpkg): running ${running}, installed ${pkgver}")
            fi
        fi
    done

    # 2. Critical packages that effectively require a full reboot
    local reboot_pkgs=(systemd glibc linux-firmware intel-ucode amd-ucode dbus)
    for pkg in "${reboot_pkgs[@]}"; do
        if echo "$ALL_UPDATED" | grep -qx "$pkg"; then
            reasons+=("${pkg} was updated")
        fi
    done

    # 3. Processes using deleted shared libraries (stale .so files in memory)
    #    /proc/PID/maps lists "(deleted)" for files that have been replaced on disk.
    local stale_services=()
    while IFS= read -r pid; do
        [[ -z "$pid" ]] && continue
        local comm
        comm=$(cat "/proc/$pid/comm" 2>/dev/null) || continue
        # Map comm names to systemd service names where obvious
        case "$comm" in
            sshd)       stale_services+=(ssh) ;;
            NetworkMana) stale_services+=(NetworkManager) ;;
            pipewire)   stale_services+=(pipewire) ;;
            wireplumber) stale_services+=(wireplumber) ;;
            bluetoothd) stale_services+=(bluetooth) ;;
            cupsd)      stale_services+=(cups) ;;
            nginx)      stale_services+=(nginx) ;;
            *)          stale_services+=("$comm") ;;
        esac
    done < <(sudo grep -rl "(deleted)" /proc/*/maps 2>/dev/null \
        | awk -F'/' '{print $3}' | sort -u)

    # Deduplicate stale_services
    if [ "${#stale_services[@]}" -gt 0 ]; then
        mapfile -t stale_services < <(printf '%s\n' "${stale_services[@]}" | sort -u)
        # If systemd or dbus are stale, escalate to full reboot
        for s in "${stale_services[@]}"; do
            if [[ "$s" == "systemd" || "$s" == "dbus" || "$s" == "dbus-daemon" ]]; then
                reasons+=("${s} process is using a deleted (replaced) library")
                stale_services=("${stale_services[@]/$s}")
            else
                restarts+=("$s")
            fi
        done
    fi

    # ── Output recommendation ──────────────────────────────────────────────────
    echo ""
    if [ "${#reasons[@]}" -gt 0 ]; then
        echo -e "  ${YELLOW}${BOLD}⚠  Reboot recommended${RESET}"
        for r in "${reasons[@]}"; do
            [[ -z "$r" ]] && continue
            echo -e "     • $r"
        done
        if [ "${#restarts[@]}" -gt 0 ]; then
            echo -e "     The following services will also need restarting after reboot:"
            for s in "${restarts[@]}"; do
                [[ -z "$s" ]] && continue
                echo -e "       – $s"
            done
        fi
    elif [ "${#restarts[@]}" -gt 0 ]; then
        echo -e "  ${CYAN}${BOLD}↻  No reboot needed — the following services need restarting:${RESET}"
        for s in "${restarts[@]}"; do
            [[ -z "$s" ]] && continue
            echo -e "     • $s"
        done
        echo ""
        echo -ne "  Restart them now? [Y/n] "
        read -r DO_RESTART
        DO_RESTART="${DO_RESTART:-Y}"
        if [[ "$DO_RESTART" =~ ^[Yy]$ ]]; then
            for s in "${restarts[@]}"; do
                [[ -z "$s" ]] && continue
                echo -ne "  restarting ${s}... "
                if sudo systemctl restart "$s" 2>/dev/null; then
                    echo -e "${GREEN}ok${RESET}"
                else
                    echo -e "${YELLOW}failed (may not be a systemd service)${RESET}"
                fi
            done
        fi
    else
        echo -e "  ${GREEN}${BOLD}✓  No reboot needed.${RESET}"
    fi
}

# ── Step 1: Gather updates before doing anything ───────────────────────────────
hdr "Checking for updates..."

REPO_LINES=$(paru -Qu --repo 2>/dev/null | grep -v '\[ignored\]') || true
AUR_LINES=$(paru -Qu --aur  2>/dev/null | grep -v '\[ignored\]') || true

REPO_COUNT=$(echo "$REPO_LINES" | grep -c '\S' 2>/dev/null || echo 0)
AUR_COUNT=$(echo  "$AUR_LINES"  | grep -c '\S' 2>/dev/null || echo 0)
# grep -c returns 1 (exit 1) when count is 0, so default to 0
[[ "$REPO_LINES" == "" ]] && REPO_COUNT=0
[[ "$AUR_LINES"  == "" ]] && AUR_COUNT=0
TOTAL=$((REPO_COUNT + AUR_COUNT))

# Package names being updated — used by checkReboot after the update
ALL_UPDATED=$({ echo "$REPO_LINES"; echo "$AUR_LINES"; } | awk '{print $1}')

if [ "$TOTAL" -eq 0 ]; then
    ok "System is up to date."
    exit 0
fi

# ── Step 2: Display update plan ────────────────────────────────────────────────
fmt_pkg_line() {
    # Input:  "pkgname 1.0 -> 2.0"   Output: "  pkgname  1.0 → 2.0"
    awk '{printf "  %-38s %s → %s\n", $1, $2, $4}'
}

echo ""
if [ "$REPO_COUNT" -gt 0 ]; then
    echo -e "${CYAN}  Repository packages${RESET} (${REPO_COUNT})"
    echo -e "${CYAN}  ────────────────────────────────────────────────────────────${RESET}"
    echo "$REPO_LINES" | fmt_pkg_line
fi
if [ "$AUR_COUNT" -gt 0 ]; then
    [ "$REPO_COUNT" -gt 0 ] && echo ""
    echo -e "${CYAN}  AUR packages${RESET} (${AUR_COUNT})"
    echo -e "${CYAN}  ────────────────────────────────────────────────────────────${RESET}"
    echo "$AUR_LINES" | fmt_pkg_line
fi

echo ""
echo -e "  ${YELLOW}${BOLD}${TOTAL} packages will be updated.${RESET} A snapshot will be created first."
echo -ne "  Proceed? [Y/n] "
read -r CONFIRM
CONFIRM="${CONFIRM:-Y}"
[[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "  Aborted."; exit 0; }

# ── Step 3: Snapshot ───────────────────────────────────────────────────────────
echo ""
hdr "Syncing /boot → /.bootbackup..."
sudo rsync -a --delete /boot/ /.bootbackup/ --quiet

MNTDIR=$(mktemp -d)
sudo mount -o subvolid=5 "$BTRFS_DEV" "$MNTDIR"
trap 'sudo umount "$MNTDIR" 2>/dev/null; rmdir "$MNTDIR" 2>/dev/null' EXIT

sudo mkdir -p "${MNTDIR}/@snapshots"

# Prune old snapshots
mapfile -t EXISTING < <(find "${MNTDIR}/@snapshots" -maxdepth 1 -name "${SNAP_PREFIX}_*" -type d | sort)
COUNT=${#EXISTING[@]}
while [ "$COUNT" -ge "$MAX_SNAPSHOTS" ]; do
    sudo btrfs subvolume delete "${EXISTING[0]}" > /dev/null
    EXISTING=("${EXISTING[@]:1}")
    COUNT=$((COUNT - 1))
done

hdr "Creating snapshot ${SNAP_NAME}..."
sudo btrfs subvolume snapshot "${MNTDIR}/@" "${MNTDIR}/@snapshots/${SNAP_NAME}" > /dev/null
ok "Snapshot created."

sudo umount "$MNTDIR"; rmdir "$MNTDIR"; trap - EXIT

hdr "Regenerating GRUB..."
sudo grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | grep -E "^(Found|done|Generating)" || true
ok "GRUB updated."

# ── Step 4: Update with progress bar ──────────────────────────────────────────
BAR_WIDTH=54

draw_bar() {
    local current=$1 total=$2
    local filled=$(( current * BAR_WIDTH / total ))
    local bar
    bar=$(printf '%*s' "$filled" '' | tr ' ' '█')
    local empty=$(( BAR_WIDTH - filled ))
    local space
    space=$(printf '%*s' "$empty" '')
    printf "\r  [${GREEN}%s${RESET}%s] %d/%d " "$bar" "$space" "$current" "$total"
}

echo ""
hdr "Updating ${TOTAL} packages..."
echo ""

# --noconfirm is safe here — user already approved above
paru -Syu --noconfirm 2>&1 | while IFS= read -r line; do
    if [[ "$line" =~ ^\(([0-9]+)/([0-9]+)\) ]]; then
        draw_bar "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    fi
done
echo ""  # newline after progress bar

# ── Step 5: Post-update GRUB ──────────────────────────────────────────────────
echo ""
hdr "Regenerating GRUB (post-update)..."
sudo grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | grep -E "^(Found|done|Generating)" || true
ok "GRUB updated."

checkReboot

echo ""
ok "Update complete.  Snapshot: ${SNAP_NAME}"
