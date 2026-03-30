# Max's Workflow System — Claude Code Handoff

## Who You're Working With

Max is a senior director and hobbyist programmer running Arch Linux with AwesomeWM. Primary tools: zsh (zinit, Starship, fzf-tab, zoxide, VI mode), Neovim, Obsidian. **Always use camelCase.** Prefers concise, correct responses. Moderate technical depth assumed — go deep on code.

---

## System Overview

A deeply integrated "second brain" combining:

- **Obsidian** — notes, tasks, knowledge base ("The Vault" at `~/Documents/The Vault`)
- **AwesomeWM** — window manager with custom Lua config at `~/.config/awesome/`
- **Dashboard server** — Python/HTTP/SSE server at `localhost:9876`, source at `~/.config/dashboard/dashboardServer.py`
- **Dashboard UI** — `~/.config/dashboard/index.html`, rendered in luakit on a secondary 1280×400 monitor
- **Eisenhower Matrix** — `~/.config/dashboard/eisenhower.html`, rendered in a luakit dropdown window
- **Theming** — pywal, colors served via `/colors.css` endpoint

---

## Key Files & Locations

### AwesomeWM

- `~/.config/awesome/rc.lua` — main config
- `~/.config/awesome/functions.lua` — all custom logic (camelCase throughout)
- `~/.config/awesome/devices/normalKeys.lua` — keyboard bindings
- `~/.config/awesome/devices/tartarus.lua` — Tartarus keypad bindings

### Dashboard Server

- `~/.config/dashboard/dashboardServer.py` — main server (port 9876)
- `~/.config/dashboard/index.html` — dashboard UI
- `~/.config/dashboard/eisenhower.html` — Eisenhower matrix + shopping list SPA
- `~/.config/dashboard/todoist.conf` — Todoist credentials (ini format, no section header)
- `~/Scripts/dashboardLaunch.sh` — kills and restarts the server, logs to `~/.cache/dashboard-server.log`

### Obsidian Vault Structure

```
The Vault/
  Daily Notes/          YYYY-MM-DD.md
  Projects/             one note per project
  People/               one note per person
  Meetings/
  Notes/                permanent notes incl. Shopping List.md
  Templates/
  Meta/                 QuickAdd scripts (captureTask.js, fileTask.js)
  Scripts/              Dataview scripts (eisenhower/)
```

### Shell Scripts (`~/Scripts/`)

- `captureTask.sh` — rofi task capture (interactive + headless via args)
- `fileTasks.sh` — rofi-based task filing loop
- `quickNotes.sh` — opens daily note ## Notes section in nvim dropdown
- `eisenhower.sh` — launches luakit eisenhower: `WEBKIT_DISABLE_DMABUF_RENDERER=1 luakit --class eisenhower --name eisenhower -U http://localhost:9876/eisenhower &`
- `dpmsInhibit.sh` — polls `playerctl status` every 30s; disables DPMS (`xset -dpms`) while playing, restores on pause/stop. Autostarted by `rc.lua` via `awful.spawn.with_shell`. Has `DEBUG_NOTIFY=false` flag.
- `dotfilesSync.sh` — syncs dotfiles to GitHub via GNU Stow
- `captureTaskRemote.sh` — remote/headless variant of captureTask
- `chooseWallpaper.sh` — wallpaper picker (pass `true` for random), triggers pywal
- `pasteFromHistory.sh` — CopyQ clipboard history via rofi
- `droidCamDaemon.sh` — DroidCam background daemon helper

---

## Task System

### Format

Tasks are plain markdown: `- [ ] Task text ⏫ [[2026-03-28]]`

- Priority via emoji: `⏫` highest, `🔼` high, `🔽` low, `⏬` lowest
- Due date as wiki-link only: `[[YYYY-MM-DD]]` (no 📅 emoji)
- Ponder tag: `#ponder` for deferred/thinking tasks

### Capture Flow

1. User triggers `captureTask.sh` (Tartarus space key or modkey+n)
2. rofi prompts for task text, due date (natural language), priority
3. If due date is `shopping` → routes to `/shopping/add` endpoint → Todoist
4. Otherwise → calls `obsidian quickadd choice="Capture Task"` → `Meta/captureTask.js` → appends to today's daily note `## Inbox`
5. Remote/headless: same script with positional args (`captureTask.sh "task" "due" "priority"`)

### Filing Flow

`fileTasks.sh` — collects unchecked tasks from Daily Notes + Meetings, lets user route them to Projects/People notes via rofi

---

## Dashboard Server Endpoints

### GET

- `/` — index.html
- `/eisenhower` — eisenhower.html
- `/eisenhower/data` — matrix JSON `{q1, q2, q3, ponder}`
- `/eisenhower/events` — SSE stream for matrix updates
- `/events` — SSE stream (sink, VPN, media, reload)
- `/status/toggles` — VPN + audio sink state
- `/status/media` — playerctl metadata
- `/status/tasks` — today's tasks array
- `/status/droidcam` — DroidCam connection state
- `/colors.css` — pywal colors
- `/shopping/items` — shopping list items array

### POST

- `/task/complete` — marks task done in vault file
- `/task/modify` — modifies task raw text in vault file
- `/obsidian/open` — `xdg-open` obsidian:// URI + xdotool focus
- `/shopping/add` — creates item in Todoist + vault
- `/shopping/complete` — closes item in Todoist + marks done in vault
- `/shopping/sync` — full Todoist → vault sync
- `/toggle/vpn` — Windscribe toggle
- `/toggle/sink` — PulseAudio sink cycle
- `/toggle/droidcam` — DroidCam connect/disconnect
- `/media/{cmd}` — playerctl commands
- `/reload` — broadcasts SSE reload to all clients
- `/webhook` — iOS Shortcut task capture (nginx basic auth)
- `/todoist/webhook` — inbound Todoist webhooks (no auth, deprecated — not firing)
- `/eisenhower/exit` — kills eisenhower luakit window

### rc.lua Autostart (via `runOnce`)

- `urxvtd`, `unclutter -root`, `~/.screenlayout/DefaultLayout.sh`
- `lxqt-policykit-agent`, `copyq`, `windscribe-cli connect`
- `bash ~/.config/dashboard/dashboardLaunch.sh`
- `zsh ~/Scripts/dpmsInhibit.sh` (spawned separately, not via runOnce)

---

## Eisenhower Matrix

Single page app at `/eisenhower`. Two views toggled by 🛒 button:

### Matrix View (default)

- **Q1 Do First** — urgent (due this week) tasks regardless of priority
- **Q2 Schedule** — unscheduled tasks (no due date)
- **Q3 Upcoming** — scheduled but not this week
- **Q4 Ponder** — tasks tagged `#ponder`
- Sorted by date then priority within each quadrant
- Shopping List.md excluded from task extraction

### Shopping List View

- Renders items from `Notes/Shopping List.md`
- Items stored as `- [ ] Item text [todoist:: TASK_ID]`
- Check = crossed out (stays until refresh) + closes in Todoist
- Text input at bottom to add new items
- Syncs with Todoist every 60 seconds via polling thread

### Task Actions (matrix)

- Checkbox → complete task, fade out
- Click task text → open file in Obsidian at line, switch tag
- 🔵 → mark as ponder
- 🎯 → set priority dropdown
- 📅 → reschedule (natural language date input)

---

## Todoist Integration

- API: `https://api.todoist.com/api/v1/` (v1, not deprecated v2)
- Credentials: `~/.config/dashboard/todoist.conf`
- Project: "Shopping List"
- Polling: 60s background thread syncs Todoist → vault
- Vault → Todoist: vault watcher detects Shopping List.md writes, calls `syncCompletedShoppingItems()` which closes completed items in Todoist
- Webhooks: configured in Todoist app console but not firing (410 on registration endpoint) — polling is the active sync mechanism

---

## Luakit Setup

Dashboard and Eisenhower both use luakit browser.

- Dashboard: `--class dashboard`, no separate instance flag needed (single monitor)
- Eisenhower: `WEBKIT_DISABLE_DMABUF_RENDERER=1 luakit --class eisenhower -U` (`-U` = separate instance)
- Status/input bars hidden via patch to `/usr/share/luakit/lib/window.lua`
- Pacman hook reapplies patch after updates

---

## AwesomeWM Dropdown System

`toggleDropdownApp(opts)` in `functions.lua`:

- `widthPct`, `heightPct` — 0.0–1.0 fractions of screen workarea
- `class` — WM_CLASS for window matching
- `spawn_cmd` — command to launch
- `ontop` set via AwesomeWM rules (not spawn_props)

Active dropdowns (use `toggleDropdownApp` in `functions.lua`):

- `modkey+t` → Dropdown terminal (kitty + tmux, `new-session -A -s dropdown`)
- `modkey+n` → Quick Notes (kitty, font_size=18.0, runs `quickNotes.sh`)
- `modkey+e` → Eisenhower matrix (luakit, 0.3×0.6, ontop=true via spawn_props)

### Rofi Interfaces

- `modkey+p` → Bitwarden CLI via rofi
- Tartarus space → `captureTask.sh` rofi prompt
- Tartarus space hold → `fileTasks.sh` rofi loop

Tag switching on window activation:

```lua
client.connect_signal("request::activate", function(c, context, hints)
    if not c:isvisible() then
        local t = c.first_tag
        if t then t:view_only() end
    end
end)
```

---

## Known Issues / Pending Work

- **luakit insert mode** — date input field in Eisenhower matrix doesn't auto-focus in luakit (normal mode). Deferred.
- **Todoist webhooks** — not firing, falling back to 60s polling. Registration endpoint HTTP 410.
- **quickNotes extraction duplication** — `## Notes` extraction logic exists in both `quickNotes.sh` (Python, startup) and `quickNotes.lua` (Lua, refresh). Could be unified into a standalone `extractNotes.py` called by both. Low priority.
- **Window grouping** — `stack.lua` still present and imported in `normalKeys.lua` (bindings: `modkey+shift+n` stack, `modkey+shift+l` list, `modkey+shift+c` clear, `modkey+shift+u` cycle). Overview previously said removed — not accurate.
- **Domain MOCs** — Work, Technical, Personal MOCs deferred.

---

## Tech Stack Summary

- **OS:** Arch Linux, X11, Nvidia GPU
- **WM:** AwesomeWM (Lua)
- **Shell:** zsh
- **Editor:** Neovim (launched via kitty+tmux: `new-session -A -s code -n NeoVim`)
- **Browser:** qutebrowser (primary, `defaultApps.browser`); Zen (`zen-browser`, secondary entry in defaultApps); luakit (`WEBKIT_DISABLE_DMABUF_RENDERER=1`) used only for dashboard and Eisenhower dropdown
- **Notes:** Obsidian (Advanced URI plugin, Templater, QuickAdd, Tasks, Dataview)
- **Tasks:** Todoist (shopping list only)
- **Media:** playerctl, D-Bus, MPRIS
- **Audio:** PipeWire/PulseAudio via pactl; two named sinks: "Headphones" (USB Audio CODEC) and "Speakers" (PCI onboard), cycled by `/toggle/sink`
- **Theming:** pywal
- **Dotfiles:** GNU Stow → `~/dotfiles` → GitHub
- **Dashboard:** Python stdlib HTTPServer, SSE, inotifywait vault watcher
- **Camera:** DroidCam CLI + HTTP API
- **VPN:** Windscribe CLI
- **Clipboard:** CopyQ
- **Nginx:** TLS termination on 443 for external webhook + iOS shortcut access

---

## Coding Conventions

- **Always camelCase** — variables, functions, filenames where applicable
- Python: snake_case is acceptable for Python (it's idiomatic) but JS/Lua/shell should be camelCase
- Lua: camelCase functions, no semicolons
- Shell: camelCase variables (avoid zsh reserved words like `status`)
- JS: camelCase everything
- Prefer incremental changes over rewrites
- Debug with flags (e.g. `DEBUG_NOTIFY=true`) designed for easy silencing
- Build up from working minimal versions rather than patching broken complex ones
