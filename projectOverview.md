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
- `bgremove.py` — GPU background removal virtual camera (RVM ONNX model, CUDA EP)
- `bgremove-setup.sh` — one-time setup: installs v4l2loopback, downloads RVM model, creates venv

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

## Background Removal Virtual Camera (bgremove)

GPU-accelerated background removal pipeline for video calls (Teams, etc.).

### Pipeline

`/dev/video20` (DroidCam) → `bgremove.py` (RVM ONNX, CUDA EP) → `/dev/video21` (VirtualCam-BG)

### Key Files

- `~/Scripts/bgremove.py` — main loop: reads v4l2 input, runs RVM inference, composites, writes to v4l2loopback output. Stays alive when DroidCam is off (outputs black placeholder so apps keep enumerating the device).
- `~/Scripts/bgremove-setup.sh` — one-time setup: installs v4l2loopback-dkms, downloads RVM MobileNetV3 ONNX model, creates Python venv at `~/.local/share/bgremove/venv`, patches pyfakewebcam for NumPy 2.x.
- `~/.config/systemd/user/bgremove.service` — user service; sets `LD_LIBRARY_PATH` for CUDA shims.
- `/etc/modprobe.d/v4l2loopback.conf` — `devices=2 video_nr=20,21 card_label="DroidCam,VirtualCam-BG" exclusive_caps=1,1` — both devices persistent on boot.

### Runtime Config

- Resolution: 1920×1080 @ 30fps, `--downsample 0.5` (model infers at 960×540)
- Background: `blur` (default); hot-reload via `echo 'green' > ~/.cache/bgremove.bg && kill -USR1 $(pgrep -f bgremove.py)`
- Mode `off` = raw passthrough (no inference)
- Dashboard controls: `GET /status/bgremove`, `POST /bgremove/mode`

### CUDA Shims (`~/.local/share/bgremove/cuda_shims/`)

onnxruntime-gpu pip wheel links against CUDA 12; system has CUDA 13. Shims bridge the gap:

- `libcufft.so.11` — compiled C shim (`cufft11_shim.c`) using `.symver` + version script to export `cufftCreate@@libcufft.so.11` etc., forwarding to real `libcufft.so.12` via dlopen
- `libcudart.so.12` → symlink to `/usr/local/lib/ollama/cuda_v12/libcudart.so.12.8.90` (Ollama ships real CUDA 12 cudart)
- `libcublas.so.12`, `libcublasLt.so.12` → symlinks to `/opt/cuda/lib64/` (already CUDA 12-compatible)
- `libcudnn.so.9` → symlink to `/usr/lib/libcudnn.so.9.20.0`
- `libcurand.so.10` — patchelf-patched copy of system lib (VERDEF already says `libcurand.so.10` ✓)

### Performance

- CUDA EP active, GPU util 56–83% during inference
- 1080p: ~22ms/frame (45fps inference headroom)
- Re-run `bgremove-setup.sh` after `paru -Syu` updates the venv's onnxruntime or pyfakewebcam

### Troubleshooting: DroidCam "Connection reset" after reboot

`droidcam-cli` errors with `Error: Connection reset! Is the app running?` even when the phone app is running. Caused by v4l2loopback module state going stale on boot.

**Prevention:** `/etc/systemd/system/v4l2loopback-reload.service` (enabled, WantedBy=multi-user.target) reloads the module fresh after `systemd-modules-load.service` and before the graphical session. bgremove.service declares `After=v4l2loopback-reload.service` to enforce ordering.

**Manual fix** (if it still occurs — bgremove must stop first so the module can unload):

```sh
systemctl --user stop bgremove.service
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback
systemctl --user start bgremove.service
# then run droidcam-cli as normal
```

`modprobe v4l2loopback` picks up options from `/etc/modprobe.d/v4l2loopback.conf` automatically (`devices=2 video_nr=20,21 card_label="DroidCam,VirtualCam-BG" exclusive_caps=1,1`).

---

## Claude Assistant Plugin

Obsidian side-panel plugin for chatting with Claude or local models. Source: `The Vault/.obsidian/plugins/claude-assistant/main.ts`.

### Backends
- **Anthropic API** — Claude models (Sonnet, Opus, Haiku) with native tool_use and prompt caching
- **Ollama** — local models via `/api/chat`; tool calling via XML (`<tool_call>` tags parsed with regex, since qwen models don't support native tool_use reliably)

### Model switching — slash commands
Type in the input box before sending:
- `/sonnet` → claude-sonnet-4-6
- `/opus` → claude-opus-4-6
- `/haiku` → claude-haiku-4-5-20251001
- `/local` → ollama (default model)
- `/7b` → ollama + qwen2.5:7b
- `/14b` → ollama + qwen2.5:14b

### Tools available to the model
- `readNote` — read full note content by path
- `createNote` — create new note
- `appendToNote` — append text to existing note
- `modifyNote` — replace full note content
- `patchFrontmatter` — patch only YAML frontmatter, body untouched (batched, one confirmation for multiple files)

All write tools require user confirmation (Apply/Cancel UI).

### Key implementation details
- **resolveFile()** — 3-tier path fallback: exact path → metadataCache link resolver → basename-only. Handles model outputting bare filenames.
- **runId cancellation** — Clear increments runId; stale async chains detect mismatch and exit. Input never left disabled.
- **Prompt injection mitigation** — `<note>` XML wrapper with DATA ONLY label, note path stamped in system prompt and prepended to every user API message.
- **Scroll** — triple setTimeout (0ms, 80ms, 250ms) after DOM mutations; needed because MarkdownRenderer layout is async.
- **Ollama history flattening** — `tool_use` blocks serialized back to XML in history so the model sees prior tool calls and doesn't loop.

### Known limitations
- **Local model transcript labeling fails** — qwen2.5:7b and 14b get prompt-injected by long transcript content despite XML DATA wrapping. Workaround: use `/haiku` (~1 cent/transcript). Potential alternatives to test: phi4:14b, llama3.1:8b.

---

## Gesture Control System

MediaPipe hand tracking → D-Bus signals → AwesomeWM/shell actions.

### Architecture

```
gestureControl.py  →  D-Bus session bus  →  gestureControl-actions.py  (shell cmds)
                   →                     →  signals.lua (AwesomeWM Lua)
```

### Key Files

- `~/Scripts/gestureControl.py` — engine: reads webcam via OpenCV/MediaPipe, detects poses/swipes/sequences/continuous metrics, emits D-Bus signals on `org.gesturecontrol.Engine`
- `~/Scripts/gestureControl-actions.py` — actions daemon: subscribes to D-Bus, dispatches shell commands per `actions.toml`
- `~/.config/awesome/signals.lua` — AwesomeWM signal handler: subscribes to D-Bus, routes to Lua functions (volume, stack cycling)
- `~/.config/gestureControl/triggers.toml` — gesture definitions: poses, bindings, cross-hand conditions
- `~/.config/gestureControl/actions.toml` — shell action bindings for the actions daemon
- `~/Scripts/gestureControl-setup.sh` — one-time setup script

### Systemd Services

Both run as systemd user services under `graphical-session.target`:

- `gestureControl.service` — engine; `PartOf=graphical-session.target`
- `gestureControl-actions.service` — daemon; `BindsTo=gestureControl.service`

Venv: `~/.local/share/gestureControl/venv/` (mediapipe, opencv-python, dbus-python)

Logs: `~/.cache/gestureControl.log`, `~/.cache/gestureControl-actions.log`

### Camera

- **IR (default):** `/dev/video2` — BRIO IR, GREY 340×340 @ 30fps
- **RGB (alt):** `/dev/video0` — BRIO RGB, MJPG 1280×720 @ 60fps (max confirmed via v4l2-ctl; 90fps not available under Linux)
- Switch via `camera = 0` / `camera = 2` in `triggers.toml`

### Trigger Types

| Type | Description |
|------|-------------|
| `pose` | Hand shape held for `dwell_ms` |
| `swipe` | Directional motion (`left` / `right`) |
| `sequence` | Ordered pose chain within `window_ms` |
| `continuous` | Metric value streamed while pose is held; emits `ContinuousUpdate` + `ContinuousEnd` |
| `chord` | Two poses held simultaneously |

**Metrics for `continuous`:** `hand_height`, `pinch_distance`, `finger_spread`, `angle` (0.0 = pointing left, 1.0 = pointing right via wrist→middle-MCP cosine)

**Cross-hand conditions:** `require_left = "POSE"` / `require_right = "POSE"` on any binding — opposite hand must hold that pose for trigger to activate. Both-hands-present suppresses single-hand triggers.

### D-Bus Signals (`org.gesturecontrol.Engine`)

- `GestureFired(name: str, hand: str)` — pose/swipe/sequence/chord triggered
- `ContinuousUpdate(name: str, hand: str, value: float)` — metric value [0.0–1.0], fires each frame
- `ContinuousEnd(name: str, hand: str)` — active_while pose released or condition dropped
- `SequenceProgress(name: str, hand: str, step: int, total: int)` — optional progress notification

### Config Hot-Reload

Both engine and actions daemon watch their config files via mtime polling (1s interval). On change: reload config, mutate state in-place. On error: keep old config, `notify-send` critical alert.

### Key Implementation Notes

- **V4L2 backend required:** `cv2.CAP_V4L2` must be passed for IR camera — GStreamer backend silently fails
- **Dark frame filter:** IR camera (Windows Hello BRIO) alternates illuminated and calibration frames at ~15fps effective. Filter: `if frame.mean() < 5.0: return` in `processFrame()`
- **Greyscale auto-detect:** `if frame.ndim == 2: frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)` before MediaPipe — IR delivers single-channel frames
- **Buffer size:** Do NOT set `CAP_PROP_BUFFERSIZE=1` on IR camera — V4L2 needs ≥2 buffers; `=1` causes near-black frames
- **`cv2.waitKey(1)`** called unconditionally every frame (required to flush OpenCV event queue even in headless mode)

### Active Bindings

| Binding | Gesture | Handler |
|---------|---------|---------|
| `tag_1`–`tag_4` | ONE–FOUR (either hand) | awesome-client tag switch |
| `prev_tag` / `next_tag` | Swipe left / right | awesome-client |
| `play_pause` | Left FIVE (300ms dwell) | playerctl play-pause |
| `set_volume` | Left FIST + right L, pinch_distance → [0.05–0.35] | `signals.lua` → `volumeControl("set", ...)` |
| `stack_cycle` | Left FIST + right ONE, angle → [0.4–0.6] | `signals.lua` → `stack.stackAll()` + `stackCycleToIndex()` |
| `stack_all` | Right FIST → THUMBS_UP sequence | awesome-client stack command |

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
- **Camera:** DroidCam CLI + HTTP API; GPU background removal via bgremove virtual camera
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
