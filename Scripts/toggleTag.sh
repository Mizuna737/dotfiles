#!/usr/bin/env bash
# Toggles visibility of a tag by its index on the focused screen.
# Usage: toggleTag.sh <tag-index>

if [[ -z "$1" ]]; then
  echo "Usage: $0 <tag-index>" >&2
  exit 1
fi

toggle_index=$1

# Send toggle command to AwesomeWM
awesome-client <<EOF
-- Get the currently focused screen
local screen = require("awful").screen.focused()
-- Fetch the tag by index
local tag = screen.tags[$toggle_index]
if tag then
  -- Toggle this tag
  require("awful").tag.viewtoggle(tag)
end
EOF
