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
            # Output is tee'd so a session's log survives past the tty scrollback.
            # Ten generations are kept, and a session that exits non-zero
            # (panic, abort) also gets a permanent copy under crashes/.
            mkdir -p ~/.cache/rubix/crashes
            for n in {9..1}; do
                [[ -f ~/.cache/rubix/session.log.$n ]] && \
                    mv ~/.cache/rubix/session.log.$n ~/.cache/rubix/session.log.$((n + 1))
            done
            [[ -f ~/.cache/rubix/session.log ]] && \
                mv ~/.cache/rubix/session.log ~/.cache/rubix/session.log.1
            ~/Projects/rubix/target/release/rubix 2>&1 | tee ~/.cache/rubix/session.log
            (( pipestatus[1] != 0 )) && \
                cp ~/.cache/rubix/session.log ~/.cache/rubix/crashes/session-$(date +%Y%m%d-%H%M%S).log
            systemctl --user stop rubix-session.target 2>/dev/null
            ;;
    esac
fi

