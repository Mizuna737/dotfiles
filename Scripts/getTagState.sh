#!/usr/bin/env bash
# awesomewm_tag_state: returns the state of a tag by its index on the focused screen.
# Usage: awesomewm_tag_state <index>

if [[ -z "$1" ]]; then
  echo "Usage: $0 <tag-index>" >&2
  exit 1
fi

index=$1

# Query AwesomeWM via awesome-client
raw=$(
  awesome-client <<EOF
-- Get the currently focused screen
local screen = require("awful").screen.focused()
-- Fetch the tag by index
local tag = screen.tags[${index}]
if not tag then
  return "invalid"
end
-- Determine state
if tag.selected then
  return "selected"
elseif tag.urgent then
  return "urgent"
elseif #tag:clients() > 0 then
  return "occupied"
else
  return "empty"
end
EOF
)

# Extract the returned string (strip leading type and quotes)
# raw looks like: string "empty"
state=${raw#*\"}  # remove up to first quote
state=${state%\"} # remove trailing quote

# Capitalize first letter
echo "${state^}"
