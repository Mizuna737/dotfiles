#!/usr/bin/env bash
# dashboardLaunch.sh
# Opens the dashboard in luakit on the secondary screen.
# Server lifecycle is managed by the dashboard.service systemd user service.
# Called from AwesomeWM autostart.

if xdotool search --classname dashboard 2>/dev/null | grep -q .; then
  echo "Dashboard already running."
  exit 0
fi

WEBKIT_DISABLE_DMABUF_RENDERER=1 luakit \
  --class dashboard \
  "http://localhost:9876" &
