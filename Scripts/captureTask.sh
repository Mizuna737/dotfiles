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
  TASK=$(rofi -dmenu -p "Capture Task" -l 0)
  [ -z "$TASK" ] && exit 0

  DUE=$(rofi -dmenu -p "Due date (e.g. 'friday', 'shopping', leave blank to skip)" -l 0) || true

  PRIORITY=$(printf "⏫ Highest\n🔼 High\n➡ Normal\n🔽 Low\n⏬ Lowest\n♥ Nicole's List\nskip" | rofi -dmenu -p "Priority" -l 7) || true
  case "$PRIORITY" in
  "⏫ Highest") PRIORITY="⏫" ;;
  "🔼 High") PRIORITY="🔼" ;;
  "➡ Normal") PRIORITY="skip" ;;
  "🔽 Low") PRIORITY="🔽" ;;
  "⏬ Lowest") PRIORITY="⏬" ;;
  "♥ Nicole's List") PRIORITY="nicole" ;;
  *) PRIORITY="skip" ;;
  esac

  DOMAIN=$(printf "#work\n#household\n#personal\nskip" | rofi -dmenu -p "Domain" -l 4) || true

  DESC=$(rofi -dmenu -p "Description (optional, blank to skip)" -l 0) || true
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

if pgrep -x obsidian > /dev/null 2>&1; then
  # Obsidian is running — hand off via URI protocol handler
  urlencode() { printf '%s' "$1" | python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read(), safe=''))"; }
  xdg-open "obsidian://quickadd?choice=$(urlencode 'Capture Task')&value-taskText=$(urlencode "$TASK")&value-dueDate=$(urlencode "$DUE")&value-priority=$(urlencode "$PRIORITY")&value-domain=$(urlencode "$DOMAIN")&value-desc=$(urlencode "$DESC")"
else
  # Obsidian is closed — write directly to the daily note file
  python3 - "$TASK" "$DUE" "$PRIORITY" "$DOMAIN" "$DESC" << 'PYEOF'
import sys, os, re
from datetime import date, timedelta

VAULT = os.path.expanduser("~/Documents/The Vault")
TEMPLATE = os.path.join(VAULT, "Templates/Daily Notes Template.md")

today = date.today()
todayStr = today.strftime("%Y-%m-%d")
notePath = os.path.join(VAULT, f"Daily Notes/{todayStr}.md")

task, due, priority, domain, desc = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

# Parse natural due date to YYYY-MM-DD
parsedDate = ""
if due and due != "skip":
    s = due.lower().strip()
    dayNames = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    if s == "today":
        parsedDate = todayStr
    elif s == "tomorrow":
        parsedDate = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif s == "next week":
        parsedDate = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    elif s in dayNames:
        diff = (dayNames.index(s) - today.weekday() + 7) % 7 or 7
        parsedDate = (today + timedelta(days=diff)).strftime("%Y-%m-%d")
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        parsedDate = s

# Build task line  (matches Capture Task.js format)
parts = [f"- [ ] {task}"]
if priority and priority != "skip":
    parts.append(priority)
if domain and domain not in ("skip", ""):
    parts.append(domain)
if desc and desc.strip():
    parts.append(f"[desc:: {desc.strip()}]")
if parsedDate:
    parts.append(f"[[{parsedDate}]]")
taskLine = " ".join(parts)

# Read or create daily note from template
if os.path.exists(notePath):
    with open(notePath, "r", encoding="utf-8") as f:
        content = f.read()
else:
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow  = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    day = today.day
    suffix = "th" if 11 <= day <= 13 else {1:"st", 2:"nd", 3:"rd"}.get(day % 10, "th")
    friendlyDate = today.strftime(f"%A, %B {day}{suffix} %Y")
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace('<% tp.date.now("YYYY-MM-DD") %>',         todayStr)
    content = content.replace('<% tp.date.yesterday("YYYY-MM-DD") %>',   yesterday)
    content = content.replace('<% tp.date.tomorrow("YYYY-MM-DD") %>',    tomorrow)
    content = content.replace('<% tp.date.now("dddd, MMMM Do YYYY") %>', friendlyDate)

# Insert task after ## Inbox header, skipping blank lines and comment lines
lines = content.split("\n")
inboxIdx = next((i for i, l in enumerate(lines) if l.strip() == "## Inbox"), None)
if inboxIdx is not None:
    insertIdx = inboxIdx + 1
    while insertIdx < len(lines) and (
        lines[insertIdx].strip() == "" or
        lines[insertIdx].strip().startswith("<!--") or
        lines[insertIdx].strip().startswith("<--")
    ):
        insertIdx += 1
else:
    insertIdx = len(lines)

lines.insert(insertIdx, taskLine)
with open(notePath, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"Captured: {task}")
PYEOF
fi
