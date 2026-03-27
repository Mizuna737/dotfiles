#!/usr/bin/env bash
set -euo pipefail

# Task text
TASK=$(rofi -dmenu -p "Capture Task" -l 0)
[ -z "$TASK" ] && exit 0

# Optional due date
DUE=$(rofi -dmenu -p "Due date (e.g. 'friday', leave blank to skip)" -l 0) || true

# Optional priority
PRIORITY=$(printf "⏫ Highest\n🔼 High\n➡ Normal\n🔽 Low\n⏬ Lowest\nskip" | rofi -dmenu -p "Priority" -l 6) || true

case "$PRIORITY" in
"⏫ Highest") PRIORITY="⏫" ;;
"🔼 High") PRIORITY="🔼" ;;
"➡ Normal") PRIORITY="skip" ;;
"🔽 Low") PRIORITY="🔽" ;;
"⏬ Lowest") PRIORITY="⏬" ;;
*) PRIORITY="skip" ;;
esac

# Treat blank due date as skip
[ -z "$DUE" ] && DUE="skip"

obsidian quickadd choice="Capture Task" vars="{\"taskText\":\"$TASK\",\"dueDate\":\"$DUE\",\"priority\":\"$PRIORITY\"}"
