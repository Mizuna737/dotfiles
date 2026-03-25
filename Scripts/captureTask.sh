#!/usr/bin/env bash
set -euo pipefail

# Prompt for task text via rofi
TASK=$(rofi -dmenu -p "Capture Task" -l 0)

# Exit if nothing entered
[ -z "$TASK" ] && exit 0

# Fire QuickAdd via Obsidian CLI
obsidian quickadd choice="Capture Task" vars="{\"taskText\":\"$TASK\"}"
