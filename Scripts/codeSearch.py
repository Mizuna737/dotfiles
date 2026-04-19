#!/usr/bin/env python3
"""codeSearch.py — Local Ollama-powered natural-language code search."""

import sys
import os
import re
import json
import time
import argparse
import subprocess
from datetime import datetime, timezone

import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.localModel import ModelSession, toonEncode, toonDecode, RingLogger

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
DEFAULT_EXTS  = {".py", ".lua", ".sh", ".js", ".ts", ".md", ".json", ".toml", ".yaml", ".yml", ".conf"}
LOG_DIR   = "/tmp/codeSearchLog"
CHUNK_SIZE    = 400
CHUNK_OVERLAP = 50
MAX_LINE_LEN  = 200
CALL_TIMEOUT  = 60  # seconds per model call


# --- TOON selftest (kept local so --selftest flag works as before) ----------

def runSelftest():
    """Round-trip a sample object list through TOON encode/decode and exit."""
    from lib.localModel import selftest
    selftest()
    sys.exit(0)


# --- File enumeration -------------------------------------------------------

def enumerateFiles(root, extFilter):
    """Use rg --files to list files, then filter by extension allowlist."""
    try:
        result = subprocess.run(
            ["rg", "--files", "--hidden", "-g", "!.git"],
            cwd=root, capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError:
        print("ripgrep (rg) not found in PATH", file=sys.stderr)
        sys.exit(2)
    paths = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        _, ext = os.path.splitext(line)
        if ext.lower() in extFilter:
            paths.append(line)
    return paths


def keywordPrefilter(root, paths, question, topN=60):
    """
    Use rg content-search to rank files by keyword hit density.
    Returns re-ordered paths with keyword-matching files first,
    capped to topN total for stage 1 model context.
    """
    keywords = [w.lower() for w in re.findall(r'\w{3,}', question) if len(w) >= 3]
    stopWords = {"the", "for", "where", "how", "does", "function", "defined",
                 "save", "logic", "task", "capture", "state", "toggle"}
    keywords = [k for k in keywords if k not in stopWords][:6]

    if not keywords:
        return paths[:topN]

    rgPattern = "|".join(re.escape(k) for k in keywords)
    try:
        result = subprocess.run(
            ["rg", "-l", "--hidden", "-g", "!.git", "-i", rgPattern],
            cwd=root, capture_output=True, text=True, timeout=20
        )
        matchingSet = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        matchingSet = set()

    questionWords = set(re.findall(r'\w{3,}', question.lower()))

    matching    = []
    nonMatching = []
    for p in paths:
        pLower    = p.lower()
        pathScore = sum(3 for k in keywords if k in pLower)
        stemScore = sum(1 for w in questionWords if w in pLower)
        inContent = p in matchingSet
        totalScore = pathScore + stemScore + (2 if inContent else 0)
        if inContent or pathScore > 0 or stemScore > 0:
            matching.append((-totalScore, p))
        else:
            nonMatching.append(p)

    matching.sort(key=lambda x: x[0])
    ordered = [p for _, p in matching] + nonMatching
    return ordered[:topN]


# --- Stage 1: file candidate selection -------------------------------------

def stage1SelectCandidates(session, question, paths, maxCandidates, verbose):
    """Ask model to pick likely-relevant file indices from the enumerated list."""
    fileRows  = [{"i": str(i), "path": p} for i, p in enumerate(paths)]
    filesToon = toonEncode("files", fileRows, ["i", "path"])

    systemPrompt = (
        "You are a code search assistant. Output ONLY integers, one per line, nothing else.\n"
        "Example (picking indices 3, 17, 42):\n"
        "3\n17\n42\n"
        "No labels, no prose, no JSON, no markdown. Just integers."
    )
    userPrompt = (
        f"Question: {question}\n\n"
        f"File list (i=index, path=file path):\n{filesToon}\n\n"
        f"Reply with at most {maxCandidates} integer indices (one per line) for files most "
        f"likely to contain code related to the question."
    )

    if verbose:
        print(f"[stage1] sending {len(paths)} files to model...", file=sys.stderr)

    rawResponse = session.generate(userPrompt, system=systemPrompt, timeout=CALL_TIMEOUT)

    if verbose:
        print(f"[stage1] FULL PROMPT:\n--- system ---\n{systemPrompt}\n--- user ---\n{userPrompt}\n--- end ---",
              file=sys.stderr)
        print(f"[stage1] FULL RESPONSE:\n{rawResponse}\n--- end ---", file=sys.stderr)

    indices = []
    seen = set()
    for token in re.findall(r'\b(\d+)\b', rawResponse):
        idx = int(token)
        if 0 <= idx < len(paths) and idx not in seen:
            seen.add(idx)
            indices.append(idx)

    candidatePaths = [paths[i] for i in indices[:maxCandidates]]

    if not candidatePaths:
        if verbose:
            print(f"[stage1] no valid indices parsed, falling back to keyword grep", file=sys.stderr)
        keywords = [w.lower() for w in re.findall(r'\w{3,}', question)]
        scored = []
        for p in paths:
            pLower = p.lower()
            score  = sum(1 for kw in keywords if kw in pLower)
            if score > 0:
                scored.append((score, p))
        scored.sort(key=lambda x: -x[0])
        candidatePaths = [p for _, p in scored[:maxCandidates]]
        if not candidatePaths:
            candidatePaths = paths[:maxCandidates]

    return candidatePaths, rawResponse, userPrompt


# --- Stage 2: line scanning ------------------------------------------------

def chunkLines(lines, chunkSize, overlap):
    """Yield (startIdx, endIdx, lineSlice) chunks with overlap."""
    total = len(lines)
    start = 0
    while start < total:
        end = min(start + chunkSize, total)
        yield start, end, lines[start:end]
        if end == total:
            break
        start = end - overlap


def stage2ScanFile(session, question, absPath, verbose):
    """
    Scan a single file for line ranges relevant to question.
    Returns list of {startLine, endLine, reason} dicts (1-based line numbers).
    """
    try:
        with open(absPath, "r", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        if verbose:
            print(f"[stage2] cannot read {absPath}: {e}", file=sys.stderr)
        return [], []

    chunks    = list(chunkLines(lines, CHUNK_SIZE, CHUNK_OVERLAP))
    allHits   = []
    chunkLogs = []

    systemPrompt = (
        "You are a code search assistant. Output ONLY lines in this exact format, nothing else:\n"
        "startLine-endLine: reason (≤10 words)\n"
        "Example:\n"
        "10-25: toggleDropdownApp function body\n"
        "87-92: dropdown initialization\n"
        "If nothing is relevant, output nothing. No JSON, no markdown, no prose."
    )

    _hitLineRe = re.compile(r'^(\d+)-(\d+):\s*(.+)$')

    for chunkStart, chunkEnd, chunkLines_ in chunks:
        lineRows = []
        for relIdx, lineText in enumerate(chunkLines_):
            absLineNo = chunkStart + relIdx + 1  # 1-based
            trimmed   = lineText.rstrip("\n")[:MAX_LINE_LEN]
            lineRows.append({"n": str(absLineNo), "text": trimmed})

        linesToon  = toonEncode("lines", lineRows, ["n", "text"])
        userPrompt = (
            f"Question: {question}\n\n"
            f"File: {absPath}\n"
            f"Lines (n=line number, text=content):\n{linesToon}\n\n"
            "Output one line per relevant range: startLine-endLine: reason\n"
            "Use the n values as startLine/endLine. If nothing is relevant, output nothing."
        )

        if verbose:
            print(f"[stage2] {os.path.basename(absPath)} chunk {chunkStart+1}-{chunkEnd}...", file=sys.stderr)

        rawResponse = session.generate(userPrompt, system=systemPrompt, timeout=CALL_TIMEOUT)

        if verbose:
            print(f"[stage2] response: {rawResponse[:200]}", file=sys.stderr)

        parsedHits = []
        for line in rawResponse.splitlines():
            line = line.strip()
            m    = _hitLineRe.match(line)
            if m:
                try:
                    sl     = int(m.group(1))
                    el     = int(m.group(2))
                    reason = m.group(3).strip()
                    if sl > 0 and el >= sl:
                        parsedHits.append({"startLine": sl, "endLine": el, "reason": reason})
                except ValueError:
                    pass
        # Fallback: try TOON if regex found nothing
        if not parsedHits:
            try:
                _, hitRows = toonDecode(rawResponse)
                for row in hitRows:
                    sl     = int(row.get("startLine", 0))
                    el     = int(row.get("endLine", 0))
                    reason = row.get("reason", "")
                    if sl > 0 and el >= sl:
                        parsedHits.append({"startLine": sl, "endLine": el, "reason": reason})
            except (ValueError, KeyError):
                pass

        chunkLogs.append({"prompt": userPrompt, "rawResponse": rawResponse, "parsedHits": parsedHits})
        allHits.extend(parsedHits)

    mergedHits = mergeRanges(allHits)
    return mergedHits, chunkLogs


def mergeRanges(hits):
    """Merge overlapping or adjacent {startLine,endLine,reason} dicts."""
    if not hits:
        return []
    sorted_ = sorted(hits, key=lambda h: h["startLine"])
    merged  = [dict(sorted_[0])]
    for h in sorted_[1:]:
        prev = merged[-1]
        if h["startLine"] <= prev["endLine"] + 1:
            prev["endLine"] = max(prev["endLine"], h["endLine"])
            if h["reason"] and h["reason"] not in prev["reason"]:
                prev["reason"] = (prev["reason"] + "; " + h["reason"])[:80]
        else:
            merged.append(dict(h))
    return merged


# --- Main ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Local Ollama code search")
    parser.add_argument("question", nargs="?", help="Natural-language question")
    parser.add_argument("--root", default=os.getcwd(), help="Root directory to search (default: cwd)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    parser.add_argument("--max-candidates", type=int, default=8, dest="maxCandidates")
    parser.add_argument("--quick", action="store_true", help="Skip stage 2 line scanning")
    parser.add_argument("--ext", default=None, help="Comma-separated extensions (default: py,lua,sh,js,ts,md,...)")
    parser.add_argument("--verbose", action="store_true", help="Debug output to stderr")
    parser.add_argument("--selftest", action="store_true", help="Run TOON codec selftest and exit")
    args = parser.parse_args()

    if args.selftest:
        runSelftest()

    if not args.question:
        parser.print_help()
        sys.exit(1)

    question = args.question
    root     = os.path.abspath(args.root)

    if args.ext:
        extFilter = {e.strip() if e.strip().startswith(".") else "." + e.strip()
                     for e in args.ext.split(",")}
    else:
        extFilter = DEFAULT_EXTS

    startTime = time.time()
    logger    = RingLogger(LOG_DIR)
    logData   = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question":  question,
        "root":      root,
        "model":     args.model,
        "mode":      "quick" if args.quick else "full",
        "elapsedMs": None,
        "stage1":    {},
        "stage2":    [],
        "finalHits": [],
    }

    if args.verbose:
        print(f"[enumerate] scanning {root}...", file=sys.stderr)
    allPaths = enumerateFiles(root, extFilter)
    if args.verbose:
        print(f"[enumerate] {len(allPaths)} files after extension filter", file=sys.stderr)

    allPaths = keywordPrefilter(root, allPaths, question, topN=60)
    if args.verbose:
        print(f"[enumerate] {len(allPaths)} files after keyword prefilter", file=sys.stderr)

    if not allPaths:
        print("No files found matching extension filter.", file=sys.stderr)
        sys.exit(1)

    finalHits = []

    with ModelSession(args.model, verbose=args.verbose) as session:
        try:
            candidatePaths, s1Raw, s1Prompt = stage1SelectCandidates(
                session, question, allPaths, args.maxCandidates, args.verbose
            )
            logData["stage1"] = {
                "prompt":         s1Prompt,
                "rawResponse":    s1Raw,
                "parsedPicks":    candidatePaths,
                "candidatePaths": candidatePaths,
            }

            if args.verbose:
                print(f"[stage1] selected {len(candidatePaths)} candidates: {candidatePaths}", file=sys.stderr)

            if args.quick:
                for relPath in candidatePaths:
                    absPath = os.path.join(root, relPath)
                    try:
                        with open(absPath, "r", errors="replace") as f:
                            lineCount = sum(1 for _ in f)
                    except OSError:
                        lineCount = 40
                    finalHits.append({
                        "path":      relPath,
                        "startLine": 1,
                        "endLine":   min(lineCount, 40),
                        "reason":    "candidate",
                    })
            else:
                stage2Logs = []
                for relPath in candidatePaths[:args.maxCandidates]:
                    absPath = os.path.join(root, relPath)
                    hitRanges, chunkLogs = stage2ScanFile(session, question, absPath, args.verbose)
                    stage2Logs.append({"path": relPath, "chunks": chunkLogs})
                    for h in hitRanges:
                        finalHits.append({
                            "path":      relPath,
                            "startLine": h["startLine"],
                            "endLine":   h["endLine"],
                            "reason":    h["reason"],
                        })
                logData["stage2"] = stage2Logs

        finally:
            elapsedMs          = int((time.time() - startTime) * 1000)
            logData["elapsedMs"]  = elapsedMs
            logData["finalHits"]  = finalHits
            logger.write(logData)

    elapsedMs = int((time.time() - startTime) * 1000)
    elapsed   = elapsedMs / 1000

    if not finalHits:
        print(f"No hits found. ({elapsed:.1f}s)", file=sys.stderr)
        sys.exit(1)

    print(f"{len(finalHits)} hit(s) found in {elapsed:.1f}s")
    hitFields = ["path", "startLine", "endLine", "reason"]
    hitRows   = [{k: str(h[k]) for k in hitFields} for h in finalHits]
    print(toonEncode("hits", hitRows, hitFields))


if __name__ == "__main__":
    main()
