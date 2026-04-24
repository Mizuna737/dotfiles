#!/bin/sh
# Wait up to 10s for DP-4 to connect; prevents AwesomeWM from binding tags
# to HDMI-0 when DP-4 enumerates late at boot.
for i in $(seq 1 20); do
    xrandr --query | grep -q "^DP-4 connected" && break
    sleep 0.5
done

xrandr --output HDMI-0 --mode 400x1280 --pos 1036x1440 --rotate right --output DP-0 --off --output DP-1 --off --output DP-2 --off --output DP-3 --off --output DP-4 --primary --mode 3440x1440 --pos 0x0 --rotate normal --output DP-5 --off
