# Commit Draft Skill

When the user asks about drafting commit messages, reviewing diffs for commits, or writing commit messages for dotfiles changes, load this skill.

## Tool

`Scripts/draftCommit.sh` (or `Scripts/draftCommit.py`)

Usage:
```
Scripts/draftCommit.sh --staged          # draft from staged changes
Scripts/draftCommit.sh --all             # draft from all changes
Scripts/draftCommit.sh --dry             # show grouped diff + TOON only
Scripts/draftCommit.sh --toonly          # TOON summary only
Scripts/draftCommit.sh --help            # show usage
```

The script:
1. Filters noise (themes, bak, locks, quickmarks, uploads, secrets)
2. Groups files by component (awesome, dashboard, scripts, config, packages)
3. Sends structured diff to local Qwen model
4. Outputs a conventional commit message draft
5. Opens editor for review, then commits and prompts for push

## Commit Message Conventions

### Format
```
type: imperative summary, ≤72 chars

- bullet 1
- bullet 2
- bullet 3 (if needed)
```

### Type
- `feat` — new capability, keybinding, script feature, new config area
- `fix` — repair something broken
- `refactor` — restructure without behavior change
- `chore` — package updates, path migrations, housekeeping
- `test` — add/modify tests

### Include
- New features/capabilities with key details (e.g. "ICS calendar parsing with RRULE expansion, Todoist/Obsidian task lists")
- New keybindings and their triggers
- Bug fixes describing what was broken
- Cross-cutting changes in ONE bullet (e.g. "migrate vault path across 6 scripts")
- Package additions listed together: "add packages: x, y, z"

### Exclude
- Auto-generated output (chooseWallpaper themes, .bak files)
- Browser bookmarks/quickmarks/history (zen, qute, vieb)
- Secrets, auth files, uploaded images
- Lock files, cache files
- Every file individually — group by logical area
- Single-line path fixes across many scripts (one bullet)

### Rules
- Imperative mood ("add", not "added")
- Each bullet starts with a verb
- Keep bullets concise but descriptive
- Output ONLY the commit message — no markdown, no explanation

## Reviewing Drafts

When the user provides a diff or asks for a commit message:
1. Read the diff with `git diff` or `git diff --staged`
2. Run `Scripts/draftCommit.sh --dry` to see grouped changes
3. Run `Scripts/draftCommit.sh --staged` (or `--all`) for a model-generated draft
4. Review the draft against the conventions above
5. If the user is working inside opencode, present the draft and let them edit

## Example

```
feat: wall widget, concord dropdown, window-to-tag, vault path migration

- add wall widget backend (dashboardServer.py): ICS calendar parsing with
  RRULE expansion, Todoist/Obsidian task lists, SSE broadcasting, image
  uploads, layout persistence
- add Concord dropdown (toggleConcord) with Mod+Ctrl+Z keybind on Tartarus
- add moveWindowToTag with Mod+Alt+Space and Mod+middle-click, hide dropdown
  classes at startup (rc.lua)
- remap arrow keys on Razer: tap cycles window focus (w/a/s/d), hold swaps
  focused window direction (Super+Ctrl+Alt)
- migrate Obsidian vault path from ~/Documents/The Vault to ~/Vault across
  all scripts and dashboard
- add packages: vieb, zen-browser-bin, electron42
- add ~/.cargo/bin to zshrc PATH
```
