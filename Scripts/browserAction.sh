#!/usr/bin/env bash
# browserAction.sh — cross-browser dispatcher for streamdeck buttons.
# Routes by focused window class so a single deck binding does the right
# thing across zen, vivaldi, qutebrowser, and vieb.
#
# Usage: browserAction.sh <action>
# Actions:
#   url       — focus URL/command bar
#   newtab    — open a new tab
#   closetab  — close current tab
#   reopen    — reopen last-closed tab
#   root      — navigate to scheme://host/ of current page
set -euo pipefail

action="${1:?action required}"
class=$(xdotool getactivewindow getwindowclassname 2>/dev/null || echo "")
classLower=${class,,}

# Clipboard-dance fallback: focus URL bar, copy URL, parse root, type it back.
# Works for browsers where Ctrl+L focuses+selects URL bar (zen, vivaldi).
clipboardDance() {
    local oldClip newUrl root
    oldClip=$(copyq read 0 2>/dev/null || true)
    xdotool key ctrl+l
    sleep 0.06
    xdotool key ctrl+c
    sleep 0.10
    newUrl=$(copyq read 0)
    root=$(python3 -c "
import sys
from urllib.parse import urlparse
u = urlparse(sys.argv[1])
if not u.scheme or not u.netloc:
    sys.exit(1)
print(f'{u.scheme}://{u.netloc}/')
" "$newUrl")
    xdotool key ctrl+a
    xdotool type --delay 0 "$root"
    xdotool key Return
    [ -n "$oldClip" ] && printf '%s' "$oldClip" | copyq copy -
}

case "$action" in
    url)
        case "$classLower" in
            qutebrowser) xdotool key o ;;
            vieb)        xdotool key e ;;
            *)           xdotool key ctrl+l ;;
        esac
        ;;
    newtab)
        case "$classLower" in
            qutebrowser) qutebrowser ":open -t about:blank" ;;
            vieb)        vieb --execute=":tabnew" >/dev/null ;;
            *)           xdotool key ctrl+t ;;
        esac
        ;;
    closetab)
        case "$classLower" in
            qutebrowser) qutebrowser ":tab-close" ;;
            vieb)        vieb --execute=":close" >/dev/null ;;
            *)           xdotool key ctrl+w ;;
        esac
        ;;
    reopen)
        case "$classLower" in
            qutebrowser) qutebrowser ":undo" ;;
            vieb)        vieb --execute=":reopen" >/dev/null ;;
            *)           xdotool key ctrl+shift+t ;;
        esac
        ;;
    root)
        case "$classLower" in
            qutebrowser) qutebrowser ":open {url:scheme}://{url:host}/" ;;
            vieb)        vieb --execute=":navigate root" >/dev/null ;;
            *)           clipboardDance ;;
        esac
        ;;
    *)
        echo "browserAction: unknown action '$action'" >&2
        exit 1
        ;;
esac
