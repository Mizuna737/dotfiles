#!/usr/bin/env bash
set -euo pipefail

p="${1-}"

# If called with no argument (can happen in some preview edge cases), do nothing.
[ -n "$p" ] || exit 0

# If fzf gives a relative path, anchor it to the current working directory.
case "$p" in
/*) : ;;
*) p="$PWD/$p" ;;
esac

if [ -d "$p" ]; then
  if command -v tree >/dev/null 2>&1; then
    tree -C -L 3 "$p" 2>/dev/null | head -300
  else
    ls -la "$p"
  fi
else
  if command -v bat >/dev/null 2>&1; then
    bat --style=numbers --color=always --line-range :300 "$p" 2>/dev/null
  else
    sed -n '1,300p' "$p"
  fi
fi
