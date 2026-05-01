#!/usr/bin/env bash
# installGitHooks.sh — symlink Scripts/gitHooks/* into .git/hooks/
# Run from the repo root (or anywhere inside the repo).

set -u

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/Scripts/gitHooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

# camelCase → dashed-lowercase conversion for git hook names
# e.g. preCommit → pre-commit, postMerge → post-merge
to_dashed() {
    local name="$1"
    # Insert a hyphen before each uppercase letter, then lowercase everything
    printf '%s' "$name" | sed 's/\([A-Z]\)/-\1/g' | tr '[:upper:]' '[:lower:]'
}

if [[ ! -d "$HOOKS_SRC" ]]; then
    printf 'error: %s does not exist\n' "$HOOKS_SRC" >&2
    exit 1
fi

shopt -s nullglob
hook_files=("$HOOKS_SRC"/*)

if [[ ${#hook_files[@]} -eq 0 ]]; then
    printf 'no hook files found in %s\n' "$HOOKS_SRC" >&2
    exit 0
fi

for src_path in "${hook_files[@]}"; do
    src_name="$(basename "$src_path")"
    dst_name="$(to_dashed "$src_name")"
    dst_path="$HOOKS_DST/$dst_name"
    # Relative symlink target from .git/hooks/ back to Scripts/gitHooks/
    rel_target="../../Scripts/gitHooks/$src_name"

    # Ensure the source hook is executable
    if [[ ! -x "$src_path" ]]; then
        chmod +x "$src_path"
        printf '[installGitHooks] chmod +x %s\n' "Scripts/gitHooks/$src_name"
    fi

    if [[ -e "$dst_path" && ! -L "$dst_path" ]]; then
        # Real file (not a symlink) — refuse to overwrite
        printf 'skipped (existing file): .git/hooks/%s — remove it manually to install\n' "$dst_name" >&2
        exit 1
    elif [[ -L "$dst_path" ]]; then
        current_target="$(readlink "$dst_path")"
        if [[ "$current_target" == "$rel_target" ]]; then
            printf 'unchanged: .git/hooks/%s\n' "$dst_name"
        else
            ln -sf "$rel_target" "$dst_path"
            printf 'replaced:  .git/hooks/%s  (was -> %s)\n' "$dst_name" "$current_target"
        fi
    else
        ln -s "$rel_target" "$dst_path"
        printf 'installed: .git/hooks/%s -> %s\n' "$dst_name" "$rel_target"
    fi
done
