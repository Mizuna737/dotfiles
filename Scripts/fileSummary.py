#!/usr/bin/env python3
"""fileSummary.py — Summarise source files with a local Ollama model."""

import sys
import os
import json
import argparse
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.localModel import ModelSession, toonEncode, toonDecode, RingLogger, selftest as libSelftest

DEFAULT_MODEL = "qwen2.5:7b-instruct"
LOG_DIR       = "/tmp/fileSummaryLog"
MAX_LINES     = 800   # trim huge files to keep prompt manageable


SYSTEM_PROMPT = """\
You are a code analysis assistant. You describe a source file as a JSON object.

Output exactly one JSON object with these four string fields:
  - path:       the file path passed to you
  - purpose:    at most 15 words describing what the file does
  - keyExports: up to 5 top-level names (functions, classes, constants), joined by commas, no spaces
  - deps:       up to 5 external imports/requires, joined by commas, no spaces

Use the single character "-" for any field that has no meaningful value.
Do not output anything except the JSON object."""


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
        f"File to summarise: {path}\n\n"
        f"<file>\n{trimmed}\n</file>\n\n"
        "Return a JSON object with fields path, purpose, keyExports, deps."
    )
    if verbose:
        print(f"[fileSummary] querying model for {path}...", file=sys.stderr)

    return session.generate(userPrompt, system=SYSTEM_PROMPT, timeout=90, format="json")


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

            # Parse the JSON object the model returned
            try:
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("not a JSON object")

                def norm(v, limit=None):
                    if v is None or v == "":
                        return "-"
                    if isinstance(v, list):
                        items = [str(x).strip() for x in v if str(x).strip()]
                        if limit:
                            items = items[:limit]
                        return ",".join(items) or "-"
                    return str(v).strip() or "-"

                row = {
                    "path":       path,  # always stamp the real path
                    "purpose":    norm(obj.get("purpose")),
                    "keyExports": norm(obj.get("keyExports"), limit=5),
                    "deps":       norm(obj.get("deps"), limit=5),
                }
                allRows.append(row)
            except (ValueError, json.JSONDecodeError):
                if args.verbose:
                    print(f"[fileSummary] JSON parse failed for {path}, raw:\n{raw}", file=sys.stderr)
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
