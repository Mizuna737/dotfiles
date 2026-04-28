#!/usr/bin/env bash
# gitCommitDraft.sh — Draft a git commit message using diffSummarize.py
# Supports auto-staging, secret scanning, and push-after-commit.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUMMARIZE="$SCRIPT_DIR/diffSummarize.py"

# ---------------------------------------------------------------------------
# 1. Check whether anything is already staged.
# ---------------------------------------------------------------------------
stagedDiff=$(git diff --staged)
userPreStaged=false
if [[ -n "$stagedDiff" ]]; then
    userPreStaged=true
fi

# ---------------------------------------------------------------------------
# 2. If nothing staged, compute what git add -A *would* add.
# ---------------------------------------------------------------------------
if [[ "$userPreStaged" == false ]]; then
    # Collect paths: modified tracked files, deleted files, untracked (non-ignored)
    mapfile -t pendingPaths < <(
        git ls-files --modified --deleted --others --exclude-standard
    )

    if [[ ${#pendingPaths[@]} -eq 0 ]]; then
        echo "nothing to commit"
        exit 0
    fi

    # -------------------------------------------------------------------------
    # 3. Secret scan on the would-be-added content.
    # -------------------------------------------------------------------------
    # Build blob: tracked diff + untracked file contents
    scanBlob=""
    trackedDiff=$(git diff 2>/dev/null || true)
    if [[ -n "$trackedDiff" ]]; then
        scanBlob+="=== tracked changes (git diff) ===
$trackedDiff
"
    fi

    repoRoot=$(git rev-parse --show-toplevel)
    totalBlobLen=${#scanBlob}
    maxTotal=20000
    maxFile=4000

    for relPath in "${pendingPaths[@]}"; do
        absPath="$repoRoot/$relPath"
        # Only append untracked (non-tracked) files that actually exist as regular files
        if git ls-files --error-unmatch "$relPath" &>/dev/null; then
            continue   # tracked — already in diff above
        fi
        [[ -f "$absPath" ]] || continue

        fileContent=$(head -c "$maxFile" "$absPath" 2>/dev/null || true)
        fileLen=${#fileContent}
        if (( totalBlobLen + fileLen + 60 > maxTotal )); then
            scanBlob+="
=== $relPath (skipped: total cap reached) ===
[truncated]
"
            break
        fi
        scanBlob+="
=== untracked: $relPath ===
$fileContent
"
        totalBlobLen=$(( totalBlobLen + fileLen + 60 ))
    done

    if [[ -n "$scanBlob" ]]; then
        scanResult=$(printf '%s' "$scanBlob" | python3 "$SUMMARIZE" --secretScan 2>/dev/null || true)
        firstLine=$(printf '%s' "$scanResult" | head -n1)

        if [[ "$firstLine" == "SECRETS_FOUND" ]]; then
            echo "" >&2
            echo "=== SECRET SCAN ALERT — aborting, nothing staged or committed ===" >&2
            printf '%s\n' "$scanResult" >&2
            echo "" >&2
            exit 1
        elif [[ "$firstLine" == "CLEAN" ]]; then
            : # all good
        else
            echo "" >&2
            echo "Secret scan returned unexpected output (neither CLEAN nor SECRETS_FOUND)." >&2
            echo "Inspect manually before committing." >&2
            echo "--- model output ---" >&2
            printf '%s\n' "$scanResult" >&2
            exit 1
        fi
    fi

    # -------------------------------------------------------------------------
    # 4. Stage everything.
    # -------------------------------------------------------------------------
    git add -A
fi

# ---------------------------------------------------------------------------
# 5. Existing flow — draft commit message.
# ---------------------------------------------------------------------------
raw=$(python3 "$SUMMARIZE" --commitMsg --staged 2>/dev/null || true)

if [[ -z "$raw" ]]; then
    echo "diffSummarize.py returned no output — is Ollama running?" >&2
    exit 1
fi

# Parse title (first non-empty line) and body (everything after blank line)
title=$(printf '%s' "$raw" | head -n1)
body=$(printf '%s' "$raw" | tail -n +3)

# Print proposed commit
echo ""
echo "=== Proposed commit ==================================="
echo "Title: $title"
echo ""
echo "$body"
echo "======================================================="
echo ""

# Prompt user
printf "[e]dit / [a]ccept / [q]uit: "
read -r -n1 choice
echo ""

commitSha=""
case "$choice" in
    a|A)
        git commit -m "$title" -m "$body"
        echo "Committed."
        commitSha=$(git rev-parse --short HEAD)
        ;;
    e|E)
        tmpFile=$(mktemp /tmp/gitcommit_XXXXXX.txt)
        printf '%s\n\n%s\n' "$title" "$body" > "$tmpFile"
        "${EDITOR:-vi}" "$tmpFile"
        editedTitle=$(head -n1 "$tmpFile")
        editedBody=$(tail -n +3 "$tmpFile")
        git commit -m "$editedTitle" -m "$editedBody"
        rm -f "$tmpFile"
        echo "Committed."
        commitSha=$(git rev-parse --short HEAD)
        ;;
    q|Q|*)
        echo "Aborted."
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# 6. Push prompt after successful commit.
# ---------------------------------------------------------------------------
echo ""
printf "push now? [Y/n]: "
read -r -n1 pushChoice
echo ""

if [[ "$pushChoice" =~ ^[nN]$ ]]; then
    echo "Not pushed. Commit: $commitSha"
    exit 0
fi

if ! git push; then
    echo "push failed — see error above" >&2
    exit $?
fi
echo "Pushed."
