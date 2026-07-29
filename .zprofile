# ~/.zprofile

# Graphical session launcher on tty1. Default to Rubix; fall back to Awesome or
# a plain shell so a broken compositor never strands the login.
if [[ -z $DISPLAY ]] && [[ -z $WAYLAND_DISPLAY ]] && [[ $(tty) == /dev/tty1 ]]; then
    print -n "Session: [R]ubix (default)  [A]wesome  [S]hell  — auto-Rubix in 5s: "
    read -t 5 -k 1 choice
    print
    case "$choice" in
        a|A) exec startx ;;
        s|S) : ;;
        *)
            # Non-exec: a compositor crash returns to this shell instead of
            # logging out. Stop the session target once Rubix exits.
            ~/Projects/rubix/target/release/rubix
            systemctl --user stop rubix-session.target 2>/dev/null
            ;;
    esac
fi

