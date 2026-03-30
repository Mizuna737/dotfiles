#!/usr/bin/env bash
set -euo pipefail

# If arguments provided, use them (remote/headless mode)
# Otherwise prompt interactively via rofi
if [ $# -ge 1 ]; then
  TASK="${1:-}"
  DUE="${2:-skip}"
  PRIORITY="${3:-skip}"
  # Map plain text priority names to emoji (for remote callers)
  case "$PRIORITY" in
  "highest") PRIORITY="⏫" ;;
  "high") PRIORITY="🔼" ;;
  "normal") PRIORITY="skip" ;;
  "low") PRIORITY="🔽" ;;
  "lowest") PRIORITY="⏬" ;;
  esac
else
  TASK=$(rofi -dmenu -p "Capture Task" -l 0)
  [ -z "$TASK" ] && exit 0

  DUE=$(rofi -dmenu -p "Due date (e.g. 'friday', 'shopping', leave blank to skip)" -l 0) || true

  PRIORITY=$(printf "⏫ Highest\n🔼 High\n➡ Normal\n🔽 Low\n⏬ Lowest\nskip" | rofi -dmenu -p "Priority" -l 6) || true
  case "$PRIORITY" in
  "⏫ Highest") PRIORITY="⏫" ;;
  "🔼 High") PRIORITY="🔼" ;;
  "➡ Normal") PRIORITY="skip" ;;
  "🔽 Low") PRIORITY="🔽" ;;
  "⏬ Lowest") PRIORITY="⏬" ;;
  *) PRIORITY="skip" ;;
  esac
fi

[ -z "$TASK" ] && exit 1

# Route to shopping list if selected
if [ "$DUE" = "shopping" ]; then
  curl -s -X POST http://localhost:9876/shopping/add \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$(echo "$TASK" | sed 's/"/\\"/g')\"}"
  exit 0
fi

[ -z "$DUE" ] && DUE="skip"

/usr/bin/obsidian quickadd choice="Capture Task" vars="{\"taskText\":\"$TASK\",\"dueDate\":\"$DUE\",\"priority\":\"$PRIORITY\"}"
