#!/bin/bash

WAL_JSON="$HOME/.cache/wal/colors.json"

if [[ ! -f "$WAL_JSON" ]]; then
  echo "Pywal colors.json not found."
  exit 1
fi

export_vars=""

# Special colors
export_vars+="export WAL_BACKGROUND=\"$(jq -r '.special.background' "$WAL_JSON")\"\n"
export_vars+="export WAL_FOREGROUND=\"$(jq -r '.special.foreground' "$WAL_JSON")\"\n"
export_vars+="export WAL_CURSOR=\"$(jq -r '.special.cursor' "$WAL_JSON")\"\n"

# 16-color palette
for i in {0..15}; do
  export_vars+="export WAL_COLOR$i=\"$(jq -r ".colors.color$i" "$WAL_JSON")\"\n"
done

# Write to a file you can source
echo -e "$export_vars" >"$HOME/.cache/wal/colors.env"
