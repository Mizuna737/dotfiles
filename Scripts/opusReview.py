#!/usr/bin/env python3
"""
opusReview.py — Pipe a spec to Opus via `claude --print` and return the review.

Usage:
    cat spec.md | python3 Scripts/opusReview.py [--round N]

Logs each call (spec excerpt + full review) to /tmp/opusReview.log.
"""

import argparse
import datetime
import subprocess
import sys

LOG_PATH = "/tmp/opusReview.log"

FRAMING = """\
You are a senior code reviewer for a local AI coding agent (opencode/Qwen3.6).
The agent has built a spec for a coding task and needs your review before implementing.

Review the spec for:
- Correctness: will this approach actually solve the stated goal?
- Risks: security, data loss, breaking changes, edge cases
- Completeness: missing steps, ambiguous deliverables, under-specified constraints
- Scope: is the agent over-reaching or under-specifying?
- Conventions: does it enforce camelCase, incremental changes, no speculative abstractions?

Respond with exactly one of:

  APPROVED
  <optional brief note if anything is worth watching during implementation>

or:

  REVISED
  ## Changes
  <concise bullet points explaining what you changed and why>

  ## Revised Spec
  <the complete corrected spec, ready to implement as-is>

Do not ask for more information. Do not say NEEDS_CHANGES. Either approve the spec or provide the corrected version yourself.
---
"""


def log(msg: str) -> None:
    with open(LOG_PATH, "a") as f:
        f.write(f"[{datetime.datetime.now().isoformat()}] {msg}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a spec to Opus for review.")
    parser.add_argument("--round", type=int, default=1, help="Review round number (1 or 2)")
    args = parser.parse_args()

    spec = sys.stdin.read().strip()
    if not spec:
        print("ERROR: empty spec on stdin", file=sys.stderr)
        sys.exit(1)

    prompt = FRAMING + spec
    excerpt = spec[:500] + ("..." if len(spec) > 500 else "")

    log(f"=== Round {args.round} spec submitted ({len(spec)} chars) ===")
    log(f"SPEC EXCERPT:\n{excerpt}")

    result = subprocess.run(
        ["claude", "--model", "claude-opus-4-7", "--print"],
        input=prompt,
        capture_output=True,
        text=True,
    )

    review = result.stdout.strip()
    log(f"REVIEW:\n{review}")
    log("=== End ===\n")

    if result.returncode != 0:
        errMsg = result.stderr.strip()
        log(f"ERROR: claude exited {result.returncode}: {errMsg}")
        print(f"ERROR: claude exited {result.returncode}: {errMsg}", file=sys.stderr)
        sys.exit(result.returncode)

    if review.upper().startswith(("APPROVED", "REVISED")):
        with open("/tmp/opus-approved", "w") as flagFile:
            flagFile.write(datetime.datetime.now().isoformat())
        log("Approval flag written to /tmp/opus-approved")

    print(review)


if __name__ == "__main__":
    main()
