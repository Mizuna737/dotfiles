#!/usr/bin/env bash
# qwenCode.sh — Run opencode non-interactively with local Qwen, suppressing the
# live event stream from the caller's context.
# Usage: qwenCode.sh [--dir PATH] [--model NAME] "prompt"
#        qwenCode.sh [--dir PATH] [--model NAME] < promptFile.txt
set -euo pipefail

DEFAULT_MODEL="local-server/qwen"

# ── help ────────────────────────────────────────────────────────────────────
usage() {
    cat >&2 <<'EOF'
Usage:
  qwenCode.sh [--dir PATH] [--model NAME] "prompt"
  qwenCode.sh [--dir PATH] [--model NAME] < promptFile.txt

Options:
  --dir   PATH   Working directory for opencode (default: $PWD)
  --model NAME   Model identifier        (default: local-server/qwen)
  -h, --help     Print this message and exit 0

Behavior:
  Runs opencode non-interactively.  The full event stream is redirected to a
  log file so it does not pollute the caller's stdout.  On success, the last
  30 lines of the log are printed to stdout as a compact summary.

Exit codes:
  0   success
  2   bad arguments / empty prompt / dir not found
  127 opencode not on PATH
  *   opencode exit code propagated
EOF
}

# ── arg parsing ─────────────────────────────────────────────────────────────
dir="$PWD"
model="$DEFAULT_MODEL"
positionalPrompt=""
positionalGiven=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --dir)
            [[ $# -lt 2 ]] && { echo "qwenCode: --dir requires an argument" >&2; exit 2; }
            dir="$2"; shift 2
            ;;
        --model)
            [[ $# -lt 2 ]] && { echo "qwenCode: --model requires an argument" >&2; exit 2; }
            model="$2"; shift 2
            ;;
        --)
            shift
            if [[ $# -gt 0 ]]; then
                positionalPrompt="$1"
                positionalGiven=1
                shift
            fi
            break
            ;;
        -*)
            echo "qwenCode: unknown option: $1" >&2
            exit 2
            ;;
        *)
            positionalPrompt="$1"
            positionalGiven=1
            shift
            ;;
    esac
done

# ── validate dir ─────────────────────────────────────────────────────────────
if [[ ! -d "$dir" ]]; then
    echo "qwenCode: directory does not exist: $dir" >&2
    exit 2
fi

# ── validate opencode on PATH ────────────────────────────────────────────────
if ! command -v opencode &>/dev/null; then
    echo "qwenCode: opencode not found on PATH" >&2
    exit 127
fi

# ── resolve prompt ───────────────────────────────────────────────────────────
stdinGiven=0
stdinPrompt=""

# Detect whether stdin is a pipe/file (not a tty)
if [[ ! -t 0 ]]; then
    stdinPrompt="$(cat)"
    [[ -n "$stdinPrompt" ]] && stdinGiven=1
fi

if [[ $positionalGiven -eq 1 && $stdinGiven -eq 1 ]]; then
    echo "qwenCode: provide prompt as positional argument OR via stdin, not both" >&2
    exit 2
fi

if [[ $positionalGiven -eq 0 && $stdinGiven -eq 0 ]]; then
    echo "qwenCode: no prompt provided (pass as argument or via stdin)" >&2
    exit 2
fi

if [[ $positionalGiven -eq 1 ]]; then
    prompt="$positionalPrompt"
else
    prompt="$stdinPrompt"
fi

if [[ -z "$prompt" ]]; then
    echo "qwenCode: prompt is empty" >&2
    exit 2
fi

# ── set up log file ──────────────────────────────────────────────────────────
timestamp=$(date +%Y%m%d-%H%M%S)
logFile="/tmp/qwenCode-${timestamp}-$$.log"
sessionFile="/tmp/qwenCode-${timestamp}-$$.session"

echo "qwenCode: dir=$dir model=$model log=$logFile" >&2

# ── invoke opencode (background so we can capture session id) ────────────────
opencode_exit=0
opencode run --model "$model" --dir "$dir" "$prompt" >"$logFile" 2>&1 &
opencode_pid=$!

# Give opencode time to create the session row in the DB
sleep 0.25
session_id=$(sqlite3 ~/.local/share/opencode/opencode.db "SELECT id FROM session ORDER BY time_created DESC LIMIT 1;" 2>/dev/null)
echo "$session_id" > "$sessionFile" 2>/dev/null
echo "qwenCode: session=$session_id" >&2

wait "$opencode_pid" || opencode_exit=$?

# ── report result ────────────────────────────────────────────────────────────
if [[ $opencode_exit -eq 0 ]]; then
    tail -n 30 "$logFile"
    echo "qwenCode: done (full log: $logFile)" >&2
    exit 0
else
    echo "qwenCode: opencode exited $opencode_exit" >&2
    echo "--- last 60 lines of $logFile ---" >&2
    tail -n 60 "$logFile" >&2
    exit $opencode_exit
fi
