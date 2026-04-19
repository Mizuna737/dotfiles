#!/usr/bin/env bash
set -euo pipefail

# If arguments provided, use them (remote/headless mode)
# Otherwise prompt interactively via rofi
if [ $# -ge 1 ]; then
  TASK="${1:-}"
  DUE="${2:-skip}"
  PRIORITY="${3:-skip}"
  DOMAIN="${4:-skip}"
  DESC="${5:-}"
  # Map plain text priority names to emoji (for remote callers)
  case "$PRIORITY" in
  "highest") PRIORITY="⏫" ;;
  "high") PRIORITY="🔼" ;;
  "normal") PRIORITY="skip" ;;
  "low") PRIORITY="🔽" ;;
  "lowest") PRIORITY="⏬" ;;
  "nicole") PRIORITY="nicole" ;;
  esac
else
  TASK=$(rofi -dmenu -i -p "Capture Task" -l 0)
  [ -z "$TASK" ] && exit 0

  DUE=$(rofi -dmenu -i -p "Due date (e.g. 'friday', 'shopping', leave blank to skip)" -l 0) || true

  PRIORITY=$(printf "⏫ Highest\n🔼 High\n➡ Normal\n🔽 Low\n⏬ Lowest\n♥ Nicole's List\nskip" | rofi -dmenu -i -p "Priority" -l 7) || true
  case "$PRIORITY" in
  "⏫ Highest") PRIORITY="⏫" ;;
  "🔼 High") PRIORITY="🔼" ;;
  "➡ Normal") PRIORITY="skip" ;;
  "🔽 Low") PRIORITY="🔽" ;;
  "⏬ Lowest") PRIORITY="⏬" ;;
  "♥ Nicole's List") PRIORITY="nicole" ;;
  *) PRIORITY="skip" ;;
  esac

  DOMAIN=$(printf "#work\n#household\n#personal\nskip" | rofi -dmenu -i -p "Domain" -l 4) || true

  DESC=$(rofi -dmenu -i -p "Description (optional, blank to skip)" -l 0) || true
fi

[ -z "$TASK" ] && exit 1

# Route to shopping list if selected
if [ "$DUE" = "shopping" ]; then
  curl -s -X POST http://localhost:9876/shopping/add \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$(echo "$TASK" | sed 's/"/\\"/g')\"}"
  exit 0
fi

# Route to Nicole's priorities if selected
if [ "$PRIORITY" = "nicole" ]; then
  DUE_FIELD=""
  if [ -n "$DUE" ] && [ "$DUE" != "skip" ]; then
    DUE_FIELD=",\"due\":\"$(echo "$DUE" | sed 's/"/\\"/g')\""
  fi
  curl -s -X POST http://localhost:9876/nicole/add \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"$(echo "$TASK" | sed 's/"/\\"/g')\"${DUE_FIELD}}"
  exit 0
fi

[ -z "$DUE" ] && DUE="skip"

"$HOME/Scripts/createtask" "$TASK" "$DUE" "$PRIORITY" "$DOMAIN" "$DESC"
