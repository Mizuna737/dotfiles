#!/usr/bin/env bash
# draftCommit.sh — Wrapper for Scripts/draftCommit.py
# Passes all arguments through to the Python script.
#
# Usage:
#   ./draftCommit.sh              # draft from all unstaged changes
#   ./draftCommit.sh --staged     # draft from staged changes
#   ./draftCommit.sh --dry        # show grouped diff + TOON only
#   ./draftCommit.sh --help       # show usage

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/draftCommit.py" "$@"
