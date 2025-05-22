#!/usr/bin/env bash
# toggleTabs.sh

# get the current value of tabs.show
cur=$(
  qutebrowser-client \
    --print-default 'config.tabs.show' \
    2>/dev/null \
  || echo ""
)

# decide the new value
if [[ "$cur" == "multiple" ]]; then
  new="switching"
else
  new="multiple"
fi

# apply it
qutebrowser-client --set "tabs.show" "$new"

# show OSD feedback
qutebrowser-client --message "tabs.show → $new"
