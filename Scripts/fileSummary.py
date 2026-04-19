#!/usr/bin/env python3
"""fileSummary.py — Summarise source files with a local Ollama model."""

import sys
import os
import argparse
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.localModel import ModelSession, toonEncode, toonDecode, RingLogger, selftest as libSelftest

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
LOG_DIR       = "/tmp/fileSummaryLog"
MAX_LINES     = 800   # trim huge files to keep prompt manageable


SYSTEM_PROMPT = """\
You are a code analysis assistant. Output ONLY a TOON block in this exact format:

summaries[1]{path,purpose,keyExports,deps}:
/some/file.py "does X and Y in ≤15 words" funcA,classB,VAR_C requests,os

Each row has exactly 4 space-separated values:
1. path — the file path (no spaces; quote if spaces present)
2. purpose — ≤15 words, quoted if multi-word (it usually will be)
3. keyExports — up to 5 top-level names, comma-separated, no spaces around commas
4. deps — up to 5 external import names, comma-separated, no spaces around commas

Use a single dash - for any field that has no meaningful value.
Output NOTHING else — no labels, no bullets, no markdown."""


def summariseFile(session, path, verbose):
    """Send file contents to the model and return its raw response."""
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"Cannot read {path}: {e}", file=sys.stderr)
        return None

    trimmed = "".join(lines[:MAX_LINES])
    if len(lines) > MAX_LINES and verbose:
        print(f"[fileSummary] {path}: trimmed to {MAX_LINES} lines", file=sys.stderr)

    userPrompt = (
        f"Summarise this file.\nPath: {path}\n\n```\n{trimmed}\n```\n\n"
        "Output the TOON block now."
    )
    if verbose:
        print(f"[fileSummary] querying model for {path}...", file=sys.stderr)

    return session.generate(userPrompt, system=SYSTEM_PROMPT, timeout=90)


def main():
    parser = argparse.ArgumentParser(description="Summarise source files via local Ollama model")
    parser.add_argument("files", nargs="*", help="File paths to summarise (or - to read list from stdin)")
    parser.add_argument("--model",    default=DEFAULT_MODEL, help="Ollama model")
    parser.add_argument("--verbose",  action="store_true",   help="Debug output on stderr")
    parser.add_argument("--selftest", action="store_true",   help="Run TOON codec selftest and exit")
    args = parser.parse_args()

    if args.selftest:
        libSelftest()
        sys.exit(0)

    # Collect file paths
    paths = []
    for arg in args.files:
        if arg == "-":
            paths.extend(line.strip() for line in sys.stdin if line.strip())
        else:
            paths.append(arg)

    if not paths:
        parser.print_help()
        sys.exit(1)

    logger   = RingLogger(LOG_DIR)
    allRows  = []
    logData  = {"model": args.model, "files": paths, "responses": []}

    with ModelSession(args.model, verbose=args.verbose) as session:
        for path in paths:
            raw = summariseFile(session, path, args.verbose)
            if raw is None:
                continue
            logData["responses"].append({"path": path, "raw": raw})

            # Parse the TOON block the model returned
            try:
                _, rows = toonDecode(raw)
                # Always stamp the real path — model often mangles it
                for row in rows:
                    row["path"] = path
                allRows.extend(rows)
            except ValueError:
                if args.verbose:
                    print(f"[fileSummary] TOON parse failed for {path}, raw:\n{raw}", file=sys.stderr)
                # Emit a placeholder row so the caller still gets something
                allRows.append({
                    "path":       path,
                    "purpose":    "parse-failed",
                    "keyExports": "-",
                    "deps":       "-",
                })

    logger.write(logData)

    if not allRows:
        print("No summaries produced.", file=sys.stderr)
        sys.exit(1)

    fields = ["path", "purpose", "keyExports", "deps"]
    # Normalise rows so all fields are present
    normRows = [{f: str(r.get(f, "-")) for f in fields} for r in allRows]
    print(toonEncode("summaries", normRows, fields))


if __name__ == "__main__":
    main()
