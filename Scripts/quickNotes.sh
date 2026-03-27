#!/usr/bin/env bash
set -euo pipefail

VAULT="/home/max/Documents/The Vault"
DAILY_NOTE="$VAULT/Daily Notes/$(date +%Y-%m-%d).md"
TEMP_FILE=$(mktemp /tmp/quicknotes-XXXXXX.md)

# Ensure daily note exists
if [ ! -f "$DAILY_NOTE" ]; then
  obsidian daily
  sleep 1
fi

# Extract ## Notes section content into temp file
DAILY_NOTE="$DAILY_NOTE" TEMP_FILE="$TEMP_FILE" python3 - <<'EOF'
import os, sys

daily_note = os.environ["DAILY_NOTE"]
temp_file = os.environ["TEMP_FILE"]

with open(daily_note, "r") as f:
    lines = f.readlines()

start_idx = next((i for i, l in enumerate(lines) if l.strip() == "## Notes"), None)

if start_idx is None:
    open(temp_file, "w").close()
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

with open(temp_file, "w") as f:
    f.writelines(content)
EOF

# Write temp file back into ## Notes section
writeback() {
  DAILY_NOTE="$DAILY_NOTE" TEMP_FILE="$TEMP_FILE" python3 - <<'EOF'
import os

daily_note = os.environ["DAILY_NOTE"]
temp_file = os.environ["TEMP_FILE"]

with open(temp_file, "r") as f:
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

# Watch temp file for changes and write back on each save
inotifywait -m -e close_write "$TEMP_FILE" 2>/dev/null | while read -r; do
  writeback
done &
WATCHER_PID=$!

# Launch nvim
DAILY_NOTE="$DAILY_NOTE" TEMP_FILE="$TEMP_FILE" \
  nvim -u "$HOME/.config/nvim/quickNotes.lua" "$TEMP_FILE"

# Nvim exited — kill watcher, do final writeback, cleanup
kill $WATCHER_PID 2>/dev/null || true
writeback
rm -f "$TEMP_FILE"
