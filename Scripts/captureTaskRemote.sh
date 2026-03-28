#!/usr/bin/env bash
set -euo pipefail

TASK="${1:-}"
DUE="${2:-skip}"
PRIORITY="${3:-skip}"

[ -z "$TASK" ] && exit 1

VAULT="/home/max/Documents/The Vault"
TODAY=$(date +%Y-%m-%d)
DAILY_NOTE="$VAULT/Daily Notes/$TODAY.md"

case "$PRIORITY" in
"highest") PRIORITY="⏫" ;;
"high") PRIORITY="🔼" ;;
"normal") PRIORITY="skip" ;;
"low") PRIORITY="🔽" ;;
"lowest") PRIORITY="⏬" ;;
esac

# Create daily note if it doesn't exist
if [ ! -f "$DAILY_NOTE" ]; then
  /usr/bin/obsidian daily
  sleep 2
  # If still doesn't exist after obsidian daily, create a minimal stub
  if [ ! -f "$DAILY_NOTE" ]; then
    cat >"$DAILY_NOTE" <<NOTEEOF
---
date: $TODAY
tags: [daily]
---

# $(date +"%A, %B %-d %Y")

## Tasks

## Unfiled Tasks

## Meetings

## Inbox

## Notes
NOTEEOF
  fi
fi

/usr/bin/obsidian quickadd choice="Capture Task" vars="{\"taskText\":\"$TASK\",\"dueDate\":\"$DUE\",\"priority\":\"$PRIORITY\"}"
