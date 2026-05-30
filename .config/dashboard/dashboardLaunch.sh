#!/usr/bin/env bash
# dashboardLaunch.sh
# Opens the dashboard in luakit on the secondary screen.
# Server lifecycle is managed by the dashboard.service systemd user service.
# Called from AwesomeWM autostart.

if xdotool search --class dashboard 2>/dev/null | grep -q .; then
  echo "Dashboard already running."
  exit 0
fi

WEBKIT_DISABLE_DMABUF_RENDERER=1 exec python3 /home/max/dotfiles/Scripts/webkitView.py \
  --class Dashboard \
  "http://localhost:9876"
