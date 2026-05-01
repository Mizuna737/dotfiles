#!/bin/bash
# updateSystem.sh — Snapshot current system, then update with single approval + progress bar
set -euo pipefail

command -v pv >/dev/null 2>&1 || { echo "error: pv is required but not installed (pacman -S pv)"; exit 1; }

# ── Colors ─────────────────────────────────────────────────────────────────────
BOLD='\033[1m'; RESET='\033[0m'
BLUE='\033[1;34m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; CYAN='\033[1;36m'

hdr()  { echo -e "${BLUE}::${RESET} ${BOLD}$*${RESET}"; }
ok()   { echo -e "${GREEN}  ✓${RESET} $*"; }

# ── Config ─────────────────────────────────────────────────────────────────────
MAX_SNAPSHOTS=3
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
hdr "Syncing package databases..."
paru -Sy 2>/dev/null

hdr "Checking for updates..."
REPO_LINES=$(paru -Qu --repo 2>/dev/null | grep -v '\[ignored\]') || true
AUR_LINES=$(paru -Qu --aur  2>/dev/null | grep -v '\[ignored\]') || true

REPO_COUNT=$(echo "$REPO_LINES" | grep -c '\S' || true)
AUR_COUNT=$(echo "$AUR_LINES"   | grep -c '\S' || true)
TOTAL=$((${REPO_COUNT:-0} + ${AUR_COUNT:-0}))

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

# ── Step 4: Update with progress bars ─────────────────────────────────────────

# Named pipes and background pids used across runWithBars; cleaned up on EXIT.
_barPipes=()
_barPids=()

trap '
    for _p in "${_barPids[@]:-}"; do kill "$_p" 2>/dev/null || true; done
    for _f in "${_barPipes[@]:-}"; do rm -f "$_f"; done
    sudo umount "$MNTDIR" 2>/dev/null || true
    rmdir "$MNTDIR" 2>/dev/null || true
' EXIT

# runWithBars pkgCount command [args...]
#   Runs command, suppresses its normal stdout, and renders two stacked pv bars:
#   - outer: one tick per installing/upgrading/reinstalling/removing event  (total = pkgCount)
#   - inner: phase progress within the current (N/M) phase, resets on new M
#   Lines that are neither (N/M) progress nor blank are forwarded to stderr so
#   warnings/errors remain visible.
runWithBars() {
    local pkgCount=$1; shift

    local outerPipe innerPipe
    outerPipe=$(mktemp -u /tmp/upd_outer_XXXXXX)
    innerPipe=$(mktemp -u /tmp/upd_inner_XXXXXX)
    mkfifo "$outerPipe" "$innerPipe"
    _barPipes+=("$outerPipe" "$innerPipe")

    # Two pv processes in cursor mode so they each own a fixed line on screen.
    pv -c -l -s "$pkgCount" -N "packages" < "$outerPipe" &
    local outerPvPid=$!
    pv -c -l -s 1          -N "phase   " < "$innerPipe" &
    local innerPvPid=$!
    _barPids+=("$outerPvPid" "$innerPvPid")

    # Open write-ends so the fifos don't EOF before we're ready.
    exec 7>"$outerPipe" 8>"$innerPipe"

    local innerPhaseSize=0
    local innerPid=""

    # Process substitution (not a pipe) keeps the while loop in the current shell,
    # so mutations to innerPhaseSize/innerPid and writes to fd 7/8 are visible here.
    while IFS= read -r line; do
        # Outer event: installing/upgrading/reinstalling/removing
        if [[ "$line" =~ ^[[:space:]]*\(([0-9]+)/([0-9]+)\)[[:space:]]+(installing|upgrading|reinstalling|removing)[[:space:]] ]]; then
            echo "" >&7   # one tick on outer bar
        fi

        # Inner phase: any (N/M) line — track M; when M changes restart inner pv
        if [[ "$line" =~ ^[[:space:]]*\(([0-9]+)/([0-9]+)\) ]]; then
            local m=${BASH_REMATCH[2]}

            if [[ "$m" != "$innerPhaseSize" ]]; then
                # New phase: close old write-end, kill old pv, start a fresh one.
                exec 8>&-
                [[ -n "$innerPid" ]] && { kill "$innerPid" 2>/dev/null || true; }
                rm -f "$innerPipe"; mkfifo "$innerPipe"
                pv -c -l -s "$m" -N "phase   " < "$innerPipe" &
                innerPid=$!
                _barPids+=("$innerPid")
                exec 8>"$innerPipe"
                innerPhaseSize=$m
            fi

            echo "" >&8   # one tick on inner bar
        elif [[ "$line" =~ [^[:space:]] ]]; then
            # Non-progress, non-blank: surface as error/warning
            echo "$line" >&2
        fi
    done < <("$@" 2>&1)

    exec 7>&- 8>&-
    wait "$outerPvPid" "$innerPvPid" 2>/dev/null || true
}

echo ""
hdr "Updating ${TOTAL} packages..."
echo ""

# --noconfirm is safe here — user already approved above
if [ "${REPO_COUNT:-0}" -gt 0 ]; then
    runWithBars "$REPO_COUNT" paru -Su --repo --noconfirm
fi
if [ "${AUR_COUNT:-0}" -gt 0 ]; then
    runWithBars "$AUR_COUNT"  paru -Su --aur  --noconfirm
fi
echo ""

# ── Step 5: Post-update GRUB ──────────────────────────────────────────────────
echo ""
hdr "Regenerating GRUB (post-update)..."
sudo grub-mkconfig -o /boot/grub/grub.cfg 2>&1 | grep -E "^(Found|done|Generating)" || true
ok "GRUB updated."

checkReboot

echo ""
ok "Update complete.  Snapshot: ${SNAP_NAME}"
