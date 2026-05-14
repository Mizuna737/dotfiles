# Agent Guide — Max's Dotfiles

## What This Is

Dotfiles managed via GNU Stow, symlinked to `~`. Arch Linux, AwesomeWM (Lua), zsh, X11, Nvidia GPU.

`projectOverview.md` in the root is the full architecture doc. Reference it before digging into config files.

## File Layout

- `~/.config/awesome/` — AwesomeWM config. Entry: `rc.lua`. Custom logic: `functions.lua` (all camelCase). Device keymaps: `devices/*.lua`
- `~/.config/dashboard/` — Python HTTP/SSE dashboard server (port 9876). UI: `index.html`, `eisenhower.html`
- `~/Scripts/` — all shell/Python scripts. Symlinked from `dotfiles/Scripts/`
- `~/Documents/The Vault/` — Obsidian vault
- `index/` — dotfiles index for lookups (run `Scripts/indexQuery.py`)
- `Scripts/` — helper scripts: `indexQuery.py`, `codeSearch.py`, `fileSummary.py`, `diffSummarize.py`, `qwenCode.sh`, `gitCommitDraft.sh`

## Gotchas

- **Stow**: files in this repo are symlinked to `~`. Don't edit `~/.config/...` directly — edit the copy here. Sync with `Scripts/dotfilesSync.sh`.
- **camelCase everywhere** except Python (snake_case is idiomatic). Lua, JS, shell, filenames: camelCase.
- `functions.lua` is the single source for dropdown apps via `toggleDropdownApp()`. Rofi and other spawned tools are NOT dropdowns.
- **Secrets are gitignored**: `adguard/`, `homeassistant/`, `todoist.conf`. Don't ask agents to read or modify these.
- **bgremove pipeline** has a fragile CUDA 12 shim layer. Re-run `Scripts/bgremove-setup.sh` after `paru -Syu` updates onnxruntime or pyfakewebcam.
- **gestureControl** requires `cv2.CAP_V4L2` backend — GStreamer backend fails on the IR camera. Buffer size must be ≥2.
- **luakit** for dashboard/Eisenhower uses a patched `/usr/share/luakit/lib/window.lua` reapplied via pacman hook.
- **System updates** go through `Scripts/updateAll.sh` (snapper snapshot → pacman → paru → reboot prompt).

## Commands

| Task | Command |
|------|---------|
| Sync dotfiles | `Scripts/dotfilesSync.sh` |
| Update system | `Scripts/updateAll.sh` |
| Restart dashboard | `Scripts/dashboardLaunch.sh` |
| Query dotfiles index | `Scripts/indexQuery.py <subcommand>` |
| Search codebase | `Scripts/codeSearch.py "query"` |
| Summarize file | `Scripts/fileSummary.py path [...]` |
| Draft commit | `Scripts/gitCommitDraft.sh` |
| Edit code | `Scripts/qwenCode.sh --dir <path> "<spec>"` |

## Repo-Specific Rules

- Never read `index/INDEX.toml` directly — use `indexQuery.py` (2000+ lines).
- Any blocking GUI process or mainloop must use `timeout N`.
- Housekeeping-only changes (.gitignore, minor config) don't need commits.
- When in conflict: config > prose. Executable source > docs.
- `~/Scripts/` scripts are the executable source of truth for system behavior.
