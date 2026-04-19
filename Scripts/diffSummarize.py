#!/usr/bin/env python3
"""diffSummarize.py — Summarise a git diff with a local Ollama model."""

import sys
import os
import re
import argparse
import subprocess
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.localModel import ModelSession, toonEncode, toonDecode, RingLogger, selftest as libSelftest

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
LOG_DIR       = "/tmp/diffSummarizeLog"
MAX_DIFF_CHARS = 12000  # trim large diffs to fit 7b context window

TOON_SYSTEM = """\
You are a code review assistant. Output ONLY a TOON block in this exact format:

changes[3]{file,kind,reason}:
src/main.py refactor "remove dead parse_date function"
README.md docs "update installation instructions"
package.json chore "bump version to 1.2.0"

Rules for each row (4 space-separated values):
1. file — the changed file path (quote if it contains spaces)
2. kind — MUST be one of: feat fix refactor docs chore test style
3. reason — ≤12 words quoted if multi-word, describing why the change exists

Output NOTHING else — no markdown, no bullets, no labels."""

COMMIT_SYSTEM = """\
You are a git commit message writer. Given a diff summary, produce:
Line 1: imperative-mood title, ≤72 characters
Line 2: blank
Lines 3+: 2-3 bullet points (each starting with "- ") describing what changed and why.
Output ONLY the commit message. No markdown headers, no extra commentary."""


def getDiff(args):
    """Return diff text from stdin, --staged, or --range."""
    if args.staged:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True, text=True, timeout=30,
            cwd=args.root,
        )
        return result.stdout
    if args.range:
        result = subprocess.run(
            ["git", "diff", args.range],
            capture_output=True, text=True, timeout=30,
            cwd=args.root,
        )
        return result.stdout
    # Default: read stdin
    return sys.stdin.read()


def main():
    parser = argparse.ArgumentParser(description="Summarise a git diff via local Ollama model")
    parser.add_argument("--staged",    action="store_true", help="Use git diff --staged")
    parser.add_argument("--range",     metavar="REF..REF",  help="Use git diff <range>")
    parser.add_argument("--commitMsg", action="store_true", help="Also emit a commit message title+body")
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--verbose",   action="store_true", help="Debug output on stderr")
    parser.add_argument("--selftest",  action="store_true", help="Run TOON codec selftest and exit")
    parser.add_argument("--root",      default=os.getcwd(), help="Git repo root for --staged/--range")
    args = parser.parse_args()

    if args.selftest:
        libSelftest()
        sys.exit(0)

    diffText = getDiff(args)
    if not diffText.strip():
        sys.exit(0)   # empty diff — nothing to do

    # Trim to fit model context; keep the start (file headers) and end (hunks)
    if len(diffText) > MAX_DIFF_CHARS:
        half = MAX_DIFF_CHARS // 2
        diffText = diffText[:half] + "\n...[diff truncated]...\n" + diffText[-half:]

    logger  = RingLogger(LOG_DIR)
    logData = {"model": args.model, "diffLen": len(diffText), "responses": {}}

    with ModelSession(args.model, verbose=args.verbose) as session:
        # --- TOON change table ---
        toonPrompt = (
            f"Diff:\n```\n{diffText}\n```\n\n"
            "Output the changes TOON block now."
        )
        if args.verbose:
            print("[diffSummarize] requesting change table...", file=sys.stderr)
        toonRaw = session.generate(toonPrompt, system=TOON_SYSTEM, timeout=90)
        logData["responses"]["toon"] = toonRaw

        # --- Commit message (optional) ---
        commitTitle = None
        commitBody  = None
        if args.commitMsg:
            if args.verbose:
                print("[diffSummarize] requesting commit message...", file=sys.stderr)
            commitRaw = session.generate(
                f"Diff:\n```\n{diffText}\n```\n\nWrite the commit message now.",
                system=COMMIT_SYSTEM,
                timeout=90,
            )
            logData["responses"]["commit"] = commitRaw
            lines = commitRaw.strip().splitlines()
            commitTitle = lines[0].strip() if lines else "chore: update code"
            # Body = everything after the blank line (line index 2+)
            bodyLines   = lines[2:] if len(lines) > 2 else []
            commitBody  = "\n".join(bodyLines).strip()

    logger.write(logData)

    # Output
    if args.commitMsg:
        # Title to stdout; body follows blank line
        print(commitTitle)
        print()
        if commitBody:
            print(commitBody)
        # TOON under --verbose so callers can capture just the commit msg
        if args.verbose:
            try:
                _, rows = toonDecode(toonRaw)
                fields  = ["file", "kind", "reason"]
                normRows = [{f: str(r.get(f, "-")) for f in fields} for r in rows]
                print(toonEncode("changes", normRows, fields), file=sys.stderr)
            except ValueError:
                print(toonRaw, file=sys.stderr)
    else:
        # Normal mode: TOON to stdout
        try:
            _, rows  = toonDecode(toonRaw)
            fields   = ["file", "kind", "reason"]
            normRows = [{f: str(r.get(f, "-")) for f in fields} for r in rows]
            print(toonEncode("changes", normRows, fields))
        except ValueError:
            print(f"[diffSummarize] model did not return valid TOON. Raw response:", file=sys.stderr)
            print(toonRaw, file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
