#!/usr/bin/env bash
set -euo pipefail

# Where the scratch text lives (pick whatever you want)
SCRATCH_FILE="${SCRATCH_FILE:-$HOME/Documents/The Vault/Quick Notes.md}"

# Minimal Neovim:
# -u NONE : no init.lua/init.vim
# -U NONE : no ginit.vim
# --clean  : skips some user config paths (redundant with -u/-U but nice)
# +'set …' : set only "writing" niceties you *do* want
exec kitty --class Quick\ Notes -e \
  nvim -u NONE -U NONE --clean \
  +"setlocal ft=markdown" \
  +"setlocal wrap linebreak" \
  +"setlocal spell" \
  +"setlocal undofile" \
  +"setlocal noswapfile" \
  "$SCRATCH_FILE"
