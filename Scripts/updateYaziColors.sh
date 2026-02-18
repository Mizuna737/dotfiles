#!/bin/bash

# Generate ~/.config/yazi/theme.toml from pywal colors

WAL_ENV="$HOME/.cache/wal/colors.env"
YAZI_THEME="$HOME/.config/yazi/theme.toml"
BACKUP="$YAZI_THEME.bak"

if [[ ! -f "$WAL_ENV" ]]; then
  echo "❌ Missing wal color export file: $WAL_ENV"
  exit 1
fi

# shellcheck disable=SC1090
source "$WAL_ENV"

mkdir -p "$(dirname "$YAZI_THEME")"

if [[ -f "$YAZI_THEME" ]]; then
  cp "$YAZI_THEME" "$BACKUP"
fi

cat >"$YAZI_THEME" <<EOF
# Auto-generated from pywal by updateYaziTheme.sh
# Source: $WAL_ENV
#
# This file intentionally overrides only a handful of high-impact UI styles.
# Anything not specified here falls back to Yazi's preset theme.

[app]
# Requires OSC 11 support (kitty supports it).
overall = { bg = "${WAL_BACKGROUND}" }

[mgr]
# CWD/header
cwd = { fg = "${WAL_COLOR4}", bold = true }

# Markers
marker_selected = { fg = "${WAL_COLOR4}", bold = true }
marker_marked   = { fg = "${WAL_COLOR6}", bold = true }
marker_copied   = { fg = "${WAL_COLOR2}", bold = true }
marker_cut      = { fg = "${WAL_COLOR1}", bold = true }

# Counts
count_selected = { fg = "${WAL_COLOR4}", bold = true }
count_copied   = { fg = "${WAL_COLOR2}" }
count_cut      = { fg = "${WAL_COLOR1}" }

# Pane borders
border_symbol = "│"
border_style  = { fg = "${WAL_COLOR8}" }

[indicator]
parent  = { fg = "${WAL_COLOR8}" }
current = { fg = "${WAL_COLOR4}" }
preview = { fg = "${WAL_COLOR6}" }

[tabs]
active   = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}", bold = true }
inactive = { fg = "${WAL_FOREGROUND}", bg = "${WAL_COLOR0}" }
sep_inner = { open = "[", close = "]" }
sep_outer = { open = "", close = "" }

[mode]
normal_main = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}", bold = true }
normal_alt  = { fg = "${WAL_FOREGROUND}", bg = "${WAL_COLOR0}" }
select_main = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR2}", bold = true }
select_alt  = { fg = "${WAL_FOREGROUND}", bg = "${WAL_COLOR0}" }
unset_main  = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR3}", bold = true }
unset_alt   = { fg = "${WAL_FOREGROUND}", bg = "${WAL_COLOR0}" }

[status]
overall         = { fg = "${WAL_FOREGROUND}", bg = "${WAL_COLOR0}" }
progress_label  = { fg = "${WAL_COLOR4}", bold = true }
progress_normal = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}" }
progress_error  = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR1}" }
perm_type  = { fg = "${WAL_COLOR6}" }
perm_read  = { fg = "${WAL_COLOR2}" }
perm_write = { fg = "${WAL_COLOR3}" }
perm_exec  = { fg = "${WAL_COLOR1}" }
perm_sep   = { fg = "${WAL_COLOR8}" }

[notify]
title_info  = { fg = "${WAL_COLOR4}", bold = true }
title_warn  = { fg = "${WAL_COLOR3}", bold = true }
title_error = { fg = "${WAL_COLOR1}", bold = true }

[pick]
border   = { fg = "${WAL_COLOR8}" }
active   = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}" }
inactive = { fg = "${WAL_FOREGROUND}", bg = "${WAL_COLOR0}" }

[input]
border   = { fg = "${WAL_COLOR8}" }
title    = { fg = "${WAL_COLOR4}", bold = true }
value    = { fg = "${WAL_FOREGROUND}" }
selected = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}" }

[cmp]
border   = { fg = "${WAL_COLOR8}" }
active   = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}" }
inactive = { fg = "${WAL_FOREGROUND}", bg = "${WAL_COLOR0}" }

[tasks]
border  = { fg = "${WAL_COLOR8}" }
title   = { fg = "${WAL_COLOR4}", bold = true }
hovered = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}" }

[help]
on      = { fg = "${WAL_COLOR4}", bold = true }
run     = { fg = "${WAL_FOREGROUND}" }
desc    = { fg = "${WAL_COLOR8}" }
hovered = { fg = "${WAL_BACKGROUND}", bg = "${WAL_COLOR4}" }
footer  = { fg = "${WAL_COLOR8}" }

[filetype]
# A small set of readable defaults that won't depend on terminal palette.
rules = [
  { mime = "image/*",            fg = "${WAL_COLOR3}" },
  { mime = "{audio,video}/*",    fg = "${WAL_COLOR5}" },
  { mime = "inode/empty",        fg = "${WAL_COLOR6}" },
  { url  = "*", is = "orphan",   fg = "${WAL_COLOR1}", bold = true },
  { url  = "*/",                fg = "${WAL_COLOR4}", bold = true },
]
EOF

echo "✅ Yazi theme updated from pywal: $YAZI_THEME"
