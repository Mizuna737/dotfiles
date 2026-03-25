#!/bin/bash

# Paths
WAL_ENV="$HOME/.cache/wal/colors.env"
THEME_FILE="$HOME/.local/share/rofi/themes/rounded-nord-dark.rasi"
BACKUP_FILE="${THEME_FILE}.bak"

# Load wal colors
if [[ ! -f "$WAL_ENV" ]]; then
  echo "No pywal environment file found at $WAL_ENV"
  exit 1
fi
source "$WAL_ENV"

# Build new content for * { ... }
REPLACEMENT_BLOCK=$(
  cat <<EOF
* {
    bg0:    ${WAL_COLOR0}33;
    bg1:    ${WAL_COLOR1};
    bg2:    ${WAL_COLOR8}80;
    bg3:    ${WAL_COLOR4}33;
    fg0:    ${WAL_FOREGROUND};
    fg1:    ${WAL_COLOR15};
    fg2:    ${WAL_FOREGROUND};
    fg3:    ${WAL_COLOR8};
}
EOF
)

# Backup theme
cp "$THEME_FILE" "$BACKUP_FILE"

# Replace first * { ... } block with new block
awk -v replacement="$REPLACEMENT_BLOCK" '
BEGIN { skip = 0; replaced = 0 }
/^\* *{/ { 
    print replacement
    skip = 1
    replaced = 1
    next
}
skip && /^\}/ { skip = 0; next }
skip == 0 { print }
END {
    if (replaced == 0) {
        print "ERROR: No * { ... } block found in theme file." > "/dev/stderr"
        exit 1
    }
}
' "$BACKUP_FILE" >"$THEME_FILE"

echo "✅ Rofi theme updated from pywal and saved to $THEME_FILE"
