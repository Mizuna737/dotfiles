#!/bin/bash

OUT="/home/max/Documents/The Vault/.obsidian/snippets/pywalColors.css"
SRC="$HOME/.cache/wal/colors.env"

# Load pywal vars
source "$SRC"

cat >"$OUT" <<EOF
/* Auto-generated from pywal */
.theme-dark {
  --background-primary: ${WAL_COLOR0};
  --background-secondary: ${WAL_COLOR1};
  --background-modifier-border: ${WAL_COLOR8};
  --text-normal: ${WAL_FOREGROUND};
  --text-muted: ${WAL_COLOR8};
  --text-accent: ${WAL_COLOR4};
  --text-on-accent: ${WAL_COLOR0};
  --interactive-accent: ${WAL_COLOR4};
  --highlight-matched-text: ${WAL_COLOR4};
  --code-background: ${WAL_COLOR0};
  --code-normal: ${WAL_COLOR6};
}
EOF

echo "✅ Obsidian pywal theme generated at $OUT"
