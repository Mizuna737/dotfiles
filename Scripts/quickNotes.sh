#!/usr/bin/env bash
set -euo pipefail

VAULT="/home/max/Documents/The Vault"
QUICKNOTES_DATE="$(date +%Y-%m-%d)"
export QUICKNOTES_DATE
DAILY_NOTE="$VAULT/Daily Notes/$QUICKNOTES_DATE.md"

# Active file is date-named. Pointer files let the watcher stay dynamic.
ACTIVE_FILE="/tmp/quicknotes-${QUICKNOTES_DATE}.md"
ACTIVE_PTR="/tmp/quicknotes-active.ptr"
DAILY_NOTE_PTR="/tmp/quicknotes-dailynote.ptr"
echo "$ACTIVE_FILE" > "$ACTIVE_PTR"
echo "$DAILY_NOTE" > "$DAILY_NOTE_PTR"

# Ensure daily note exists
if [ ! -f "$DAILY_NOTE" ]; then
  obsidian daily
  sleep 1
fi

# Extract ## Notes section content into active file
DAILY_NOTE="$DAILY_NOTE" ACTIVE_FILE="$ACTIVE_FILE" python3 - <<'EOF'
import os, sys

daily_note = os.environ["DAILY_NOTE"]
active_file = os.environ["ACTIVE_FILE"]

with open(daily_note, "r") as f:
    lines = f.readlines()

start_idx = next((i for i, l in enumerate(lines) if l.strip() == "## Notes"), None)

if start_idx is None:
    open(active_file, "w").close()
    sys.exit(0)

end_idx = next(
    (i for i in range(start_idx + 1, len(lines)) if lines[i].startswith("## ")),
    len(lines)
)

content = lines[start_idx + 1:end_idx]
while content and content[0].strip() == "":
    content.pop(0)
while content and content[-1].strip() == "":
    content.pop()

with open(active_file, "w") as f:
    f.writelines(content)
EOF

# Write active file back into ## Notes section of whichever daily note the pointer says
writeback() {
  ACTIVE_PTR="$ACTIVE_PTR" DAILY_NOTE_PTR="$DAILY_NOTE_PTR" python3 - <<'EOF'
import os

active_file = open(os.environ["ACTIVE_PTR"]).read().strip()
daily_note = open(os.environ["DAILY_NOTE_PTR"]).read().strip()

with open(active_file, "r") as f:
    new_content = f.readlines()

with open(daily_note, "r") as f:
    lines = f.readlines()

start_idx = next((i for i, l in enumerate(lines) if l.strip() == "## Notes"), None)

if start_idx is None:
    lines.append("\n## Notes\n")
    start_idx = len(lines) - 1

end_idx = next(
    (i for i in range(start_idx + 1, len(lines)) if lines[i].startswith("## ")),
    len(lines)
)

new_lines = (
    lines[:start_idx + 1] +
    ["\n"] +
    new_content +
    (["\n"] if new_content and not new_content[-1].endswith("\n") else []) +
    ["\n"] +
    lines[end_idx:]
)

with open(daily_note, "w") as f:
    f.writelines(new_lines)
EOF
}

# Watch /tmp/ for writes to any quicknotes file. Checks against the active pointer
# on each event so it automatically follows file switches without restarting.
inotifywait -m -e close_write /tmp/ 2>/dev/null | while read -r dir event file; do
  if [[ "$file" == quicknotes-*.md ]]; then
    activeFile="$(cat "$ACTIVE_PTR" 2>/dev/null)"
    if [[ "/tmp/$file" == "$activeFile" ]]; then
      writeback
    fi
  fi
done &
WATCHER_PID=$!

# Launch nvim
nvim -u "$HOME/.config/nvim/quickNotes.lua" "$ACTIVE_FILE"

# Nvim exited — kill watcher, do final writeback, cleanup
kill $WATCHER_PID 2>/dev/null || true
writeback
rm -f "$ACTIVE_FILE" "$ACTIVE_PTR" "$DAILY_NOTE_PTR"
