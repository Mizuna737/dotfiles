#!/usr/bin/env bash
# gitCommitDraft.sh — Draft a git commit message using diffSummarize.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUMMARIZE="$SCRIPT_DIR/diffSummarize.py"

# 1. Check for staged changes
diff=$(git diff --staged)
if [[ -z "$diff" ]]; then
    echo "nothing staged"
    exit 0
fi

# 2. Pipe staged diff through diffSummarize.py --commitMsg
# Capture output: line 1 = title, rest = body
raw=$(echo "$diff" | python3 "$SUMMARIZE" --commitMsg --staged 2>/dev/null || true)

if [[ -z "$raw" ]]; then
    echo "diffSummarize.py returned no output — is Ollama running?" >&2
    exit 1
fi

# Parse title (first non-empty line) and body (everything after blank line)
title=$(echo "$raw" | head -n1)
body=$(echo "$raw" | tail -n +3)

# 3. Print proposed commit
echo ""
echo "=== Proposed commit ==================================="
echo "Title: $title"
echo ""
echo "$body"
echo "======================================================="
echo ""

# 4. Prompt user
printf "[e]dit / [a]ccept / [q]uit: "
read -r -n1 choice
echo ""

case "$choice" in
    a|A)
        git commit -m "$title" -m "$body"
        echo "Committed."
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
        ;;
    q|Q|*)
        echo "Aborted."
        exit 1
        ;;
esac
