#!/usr/bin/env bash
PRES="file://$HOME/Downloads/presentation.html"

# Hook manage signal BEFORE spawning so we don't miss the window
awesome-client '
  local count = 0
  local function onManage(c)
    if c.class == "qutebrowser" then
      count = count + 1
      c.floating = true
      if count == 1 then
        c:geometry({ x = 0, y = 0, width = 1920, height = 1080 })
      end
      if count >= 2 then
        client.disconnect_signal("manage", onManage)
      end
    end
  end
  client.connect_signal("manage", onManage)
'

# Open presentation in a new window, hiding chrome via qutebrowser commands
qutebrowser --target window \
  -s statusbar.show never \
  -s tabs.show never \
  "$PRES" &

# Open notes in another new window with normal chrome
sleep 1 && qutebrowser --target window "${PRES}#notes"
