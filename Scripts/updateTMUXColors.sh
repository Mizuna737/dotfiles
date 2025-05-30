#!/bin/bash

# Paths
WAL_ENV="$HOME/.cache/wal/colors.env"
TMUX_THEME="$HOME/.config/tmux/plugins/tmux-ayu-theme/tmux-ayu-theme.tmux"
BACKUP="$TMUX_THEME.bak"

# Check for wal color env
if [[ ! -f "$WAL_ENV" ]]; then
  echo "❌ Missing wal color export file: $WAL_ENV"
  exit 1
fi

# Source wal colors
source "$WAL_ENV"

# Backup current tmux theme
cp "$TMUX_THEME" "$BACKUP"

# Define new ayu-style color assignments
REPLACEMENT=$(
  cat <<EOF
ayu_black="${WAL_COLOR0}"
ayu_blue="${WAL_COLOR4}"
ayu_yellow="${WAL_COLOR3}"
ayu_red="${WAL_COLOR1}"
ayu_white="${WAL_COLOR7}"
ayu_green="${WAL_COLOR2}"
ayu_visual_grey="${WAL_COLOR8}"
ayu_comment_grey="${WAL_COLOR8}"
EOF
)

# Replace first block of color assignments in the file (up to first blank line or non-assignment)
awk -v block="$REPLACEMENT" '
BEGIN { replaced = 0 }
/^ayu_.*="#[0-9a-fA-F]{6}"$/ {
  if (!replaced) {
    print block
    replaced = 1
  }
  next
}
{ print }
' "$BACKUP" >"$TMUX_THEME"

echo "✅ Tmux theme updated from pywal: $TMUX_THEME"
