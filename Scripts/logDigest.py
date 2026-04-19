#!/usr/bin/env python3
"""logDigest.py — Digest a log file with a local Ollama model."""

import sys
import re
import argparse
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.localModel import ModelSession, toonEncode, toonDecode, RingLogger, selftest as libSelftest

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
LOG_DIR       = "/tmp/logDigestLog"
MAX_LINES     = 2000   # tail to this many lines if log is larger

SYSTEM_PROMPT = """\
You are a log analysis assistant. Output ONLY a TOON block in this exact format:

summary[1]{errorCount,warnCount,topCategories,firstFatalLine,firstFatalText}:
42 7 "database;network;auth" 312 "FATAL disk write failed: no space left"

The single data row has exactly 5 space-separated values:
1. errorCount — integer (you may write 0; the caller will override with real count)
2. warnCount  — integer (you may write 0; the caller will override with real count)
3. topCategories — up to 3 categories separated by semicolons, quoted (e.g. "network;auth;disk")
4. firstFatalLine — line number of first FATAL/fatal/critical entry, or - if none
5. firstFatalText — first 80 chars of that line, quoted, or - if none

Output NOTHING else — no labels, no bullets, no markdown."""


def readLog(args):
    """Return last MAX_LINES lines of log text."""
    if args.file:
        try:
            with open(args.file, "r", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            print(f"Cannot read {args.file}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        lines = sys.stdin.readlines()

    if len(lines) > MAX_LINES:
        lines = lines[-MAX_LINES:]
    return "".join(lines)


def preCount(text):
    """
    Cheap regex pre-count of errors/warnings.
    These values override whatever the model guesses — model is unreliable
    for exact counts but better at categories and fatal detection.
    """
    errorCount = len(re.findall(r'\b(?:error|ERROR|Error)\b', text))
    warnCount  = len(re.findall(r'\b(?:warn(?:ing)?|WARN(?:ING)?)\b', text))
    return errorCount, warnCount


def main():
    parser = argparse.ArgumentParser(description="Digest a log file via local Ollama model")
    parser.add_argument("--file",     metavar="PATH", help="Log file path (default: stdin)")
    parser.add_argument("--model",    default=DEFAULT_MODEL)
    parser.add_argument("--verbose",  action="store_true", help="Debug output on stderr")
    parser.add_argument("--selftest", action="store_true", help="Run TOON codec selftest and exit")
    args = parser.parse_args()

    if args.selftest:
        libSelftest()
        sys.exit(0)

    logText            = readLog(args)
    realErrorCount, realWarnCount = preCount(logText)

    logger  = RingLogger(LOG_DIR)
    logData = {"model": args.model, "logLen": len(logText), "responses": {}}

    with ModelSession(args.model, verbose=args.verbose) as session:
        userPrompt = (
            f"Log text:\n```\n{logText}\n```\n\n"
            "Output the summary TOON block now."
        )
        if args.verbose:
            print("[logDigest] querying model...", file=sys.stderr)
        raw = session.generate(userPrompt, system=SYSTEM_PROMPT, timeout=120)
        logData["responses"]["raw"] = raw

    logger.write(logData)

    try:
        _, rows = toonDecode(raw)
        row     = rows[0] if rows else {}
    except ValueError:
        if args.verbose:
            print(f"[logDigest] TOON parse failed, raw:\n{raw}", file=sys.stderr)
        row = {}

    # Override counts with real pre-counted values (model often hallucinates these)
    row["errorCount"] = str(realErrorCount)
    row["warnCount"]  = str(realWarnCount)

    fields   = ["errorCount", "warnCount", "topCategories", "firstFatalLine", "firstFatalText"]
    normRow  = {f: str(row.get(f, "-")) for f in fields}
    print(toonEncode("summary", [normRow], fields))


if __name__ == "__main__":
    main()
