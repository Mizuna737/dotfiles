# Agent Guide — Max's Dotfiles

## MANDATORY WORKFLOW

**FOLLOW THESE STEPS IN ORDER. SKIPPING ANY STEP IS NOT PERMITTED.**

**YOU ARE NOT PERMITTED to use Edit, Write, or file-modifying Bash commands until `opusReview.py` has returned `APPROVED` in this session.**

For any task that modifies files (> ~5 lines or multiple files):

### STEP 1 — EXPLORE
Read relevant files, search for context, understand the system before forming a plan.

### STEP 2 — WRITE SPEC
Follow `~/.claude/specTemplate.md`. Write spec to `/tmp/opencode-spec-$(date +%s).md`.

### STEP 3 — OPUS REVIEW (REQUIRED GATE — DO NOT SKIP)

Call the `opus_review` MCP tool:
- `spec`: full contents of the spec from Step 2
- `round`: 1 for first submission, 2 for revised

STOP. Wait for the response. DO NOT proceed until you receive `APPROVED` or `REVISED`.

- If `APPROVED`: proceed to Step 4 using your original spec.
- If `REVISED`: Opus has returned a corrected spec. Use the content under `## Revised Spec` as your implementation target instead of your original. Proceed to Step 4.
- If neither: STOP. Report the unexpected response to the user. DO NOT implement.

### STEP 4 — IMPLEMENT
Only after `APPROVED`. Follow the spec exactly. No additions or improvements outside scope.

### STEP 5 — VERIFY
Run the verification commands from the spec.

### STEP 6 — STOP
Do not commit. Report: files changed, verification results, open questions.

---

**Exception — skip Opus review ONLY when the user explicitly says one of:**
- "skip review" / "just do it" / "no review"
- Change is < ~5 lines (typo, rename, single comment)
- Iterating on a previously approved spec with only minor corrections

## What This Is

Dotfiles managed via GNU Stow, symlinked to `~`. Arch Linux, AwesomeWM (Lua), zsh, X11, Nvidia GPU.

`projectOverview.md` in the root is the full architecture doc. Reference it before digging into config files.

## File Layout

- `~/.config/awesome/` — AwesomeWM config. Entry: `rc.lua`. Custom logic: `functions.lua` (all camelCase). Device keymaps: `devices/*.lua`
- `~/.config/dashboard/` — Python HTTP/SSE dashboard server (port 9876). UI: `index.html`, `eisenhower.html`
- `~/Scripts/` — all shell/Python scripts. Symlinked from `~/Projects/dotfiles-tools/Scripts/`
- `~/Documents/The Vault/` — Obsidian vault
- `index/` — dotfiles index for lookups (run `~/Scripts/indexQuery.py`)
- `~/Scripts/` — helper scripts: `indexQuery.py`, `codeSearch.py`, `fileSummary.py`, `diffSummarize.py`, `qwenCode.sh`, `gitCommitDraft.sh`, `opusReview.py`

## Available Scripts

| Job | Script |
|-----|--------|
| Structural lookup over dotfiles index | `~/Scripts/indexQuery.py` |
| One-shot Qwen reasoning | `~/Scripts/qwenAsk.py "question"` (`--think` for harder problems) |
| Symbol / how-does-Y-work lookup | `~/Scripts/codeSearch.py "question"` |
| Summarize a code file | `~/Scripts/fileSummary.py path [...]` |
| Draft commit message / summarize diff | `~/Scripts/diffSummarize.py [--staged\|--range A..B] [--commitMsg]` |
| Triage a log file | `~/Scripts/logDigest.py --file PATH` |
| Submit spec to Opus for review | `~/Scripts/opusReview.py --round N` (pipe spec on stdin) |
| Sync dotfiles | `~/Scripts/dotfilesSync.sh` |
| Update system | `~/Scripts/updateAll.sh` |
| Restart dashboard | `~/Scripts/dashboardLaunch.sh` |
| Interactive commit drafter | `~/Scripts/gitCommitDraft.sh` |

Always try `indexQuery.py` first for lookups — pure grep, zero cost. Fall through to `codeSearch.py` when the index doesn't know. NEVER read `index/INDEX.toml` directly — it's 2000+ lines.

```
~/Scripts/indexQuery.py — read-only query over the dotfiles index.
  tags AWESOME[,DASHBOARD]   files carrying any tag (--all = AND)
  file PATH                  full entry for one file
  symbol NAME                symbol → file:line (prefix match; --exact)
  search "QUERY"             substring match on purpose (--tag X to scope)
  deps MODULE                reverse-dep lookup
  exports TAG                all exports from files in TAG
  stats                      index health summary
```

## Gotchas

- **Stow**: files in this repo are symlinked to `~`. Don't edit `~/.config/...` directly — edit the copy here. Sync with `~/Scripts/dotfilesSync.sh`.
- **camelCase everywhere**: Lua, JS, Python, shell variables, filenames. No exceptions.
- `functions.lua` is the single source for dropdown apps via `toggleDropdownApp()`. Rofi and other spawned tools are NOT dropdowns.
- **Secrets are gitignored**: `adguard/`, `homeassistant/`, `todoist.conf`. Don't read or modify these.
- **bgremove pipeline** has a fragile CUDA 12 shim layer. Re-run `~/Scripts/bgremove-setup.sh` after `paru -Syu` updates onnxruntime or pyfakewebcam.
- **gestureControl** requires `cv2.CAP_V4L2` backend — GStreamer backend fails on the IR camera. Buffer size must be ≥2.
- **luakit** for dashboard/Eisenhower uses a patched `/usr/share/luakit/lib/window.lua` reapplied via pacman hook.
- **System updates** go through `~/Scripts/updateAll.sh` (snapper snapshot → pacman → paru → reboot prompt).

## Code Conventions

- camelCase everywhere: Lua, JS, Python, shell variables, filenames
- Incremental changes only — no rewrites
- No speculative abstractions — solve what's asked
- Remove DEBUG flags before shipping
- Anticipate ordering/uniqueness edge cases (sorts need tiebreakers, sets need dedup, indices need bounds checks)
- No comments unless the WHY is non-obvious (hidden constraint, workaround, subtle invariant)
- When scanning for artifacts, check both `~/dotfiles/` AND deployed locations (`~/.config/`, `~/.local/`). Stow symlinks can break.
- Any shell command that could hang must use `timeout N` or equivalent.
- Housekeeping-only changes (.gitignore, minor config) don't need commits or pushes.
- When in conflict: config > prose. Executable source > docs.
- When iterating on a code snippet or query, auto-copy each new version to clipboard via `copyq copy`.

## After Implementation

Stop. Do not commit. Report:
- What files were changed and how
- Verification results
- Any open questions or risks noticed during implementation
