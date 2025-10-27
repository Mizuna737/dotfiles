#!/bin/bash

OUT="$HOME/.config/zen/pywal.css"
SRC="$HOME/.cache/wal/colors.env"

# Load pywal vars
source "$SRC"

mkdir -p "$(dirname "$OUT")"

cat >"$OUT" <<EOF
/* Zen Browser Pywal Theme */
body {
  background-color: ${WAL_COLOR0};
  color: ${WAL_FOREGROUND};
}

a {
  color: ${WAL_COLOR4};
}

code, pre {
  background-color: ${WAL_COLOR1};
  color: ${WAL_COLOR7};
}

::selection {
  background: ${WAL_COLOR4};
  color: ${WAL_COLOR0};
}
EOF

echo "✅ Zen Browser CSS theme generated at $OUT"
