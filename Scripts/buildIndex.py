#!/usr/bin/env python3
"""buildIndex.py — Build token-efficient INDEX.toml and SYMBOLS.tsv for the dotfiles repo."""

import sys
import os
import re
import json
import hashlib
import argparse
import subprocess
import pathlib
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.localModel import ModelSession, RingLogger

DEFAULT_MODEL  = "qwen2.5-coder:7b-instruct-q4_K_M"
LOG_DIR        = "/tmp/buildIndexLog"
REPO_ROOT      = str(pathlib.Path(__file__).resolve().parent.parent)
INDEX_DIR      = os.path.join(REPO_ROOT, "index")
INDEX_TOML     = os.path.join(INDEX_DIR, "INDEX.toml")
SYMBOLS_TSV    = os.path.join(INDEX_DIR, "SYMBOLS.tsv")
MAX_FILE_BYTES = 12 * 1024   # 12KB prompt cap
SKIP_SIZE_BYTES = 256 * 1024  # 256KB skip threshold
BINARY_SNIFF_BYTES = 8 * 1024  # bytes to check for NUL

LOCKED_TAGS = [
    "awesome", "dashboard", "bgremove", "gesture", "fanControl",
    "workspace", "script", "systemd", "obsidian", "shell",
    "packages", "claude", "audio", "input", "dotfile",
]
LOCKED_TAG_SET = set(LOCKED_TAGS)

SKIP_FILENAME_PATTERNS = re.compile(
    r'(\.lock|\.lockb|package-lock\.json|yarn\.lock|poetry\.lock|Cargo\.lock|\.min\.js|\.min\.css)$'
)

# Few-shot examples embedded in the Qwen prompt
FEW_SHOT_EXAMPLES = """
Example 1 — AwesomeWM Lua helper:
File: .config/awesome/functions.lua  Language: Lua
{
  "purpose": "Window/tag/dropdown helpers for AwesomeWM",
  "tags": ["awesome", "input"],
  "exports": ["toggleDropdownApp", "moveToTag", "smartFocus"],
  "deps": ["workspaceManager", "awful"]
}

Example 2 — Python systemd daemon:
File: Scripts/bgremove.py  Language: Python
{
  "purpose": "Background removal daemon using TensorRT inference on webcam frames",
  "tags": ["bgremove", "systemd"],
  "exports": ["main", "InferenceWorker"],
  "deps": ["droidcam", "bgremove.service"]
}
""".strip()

SYSTEM_PROMPT = """\
You are a code analysis assistant. Analyse the provided source file and return a JSON object.

Respond with ONLY a JSON object — no markdown, no explanation, no extra text.

Required fields:
  "purpose"  — one line, ≤120 chars, no trailing period, describing what this file does
  "tags"     — JSON array; pick 1-5 tags from THIS LIST ONLY (no others):
               awesome, dashboard, bgremove, gesture, fanControl, workspace,
               script, systemd, obsidian, shell, packages, claude, audio, input, dotfile
  "exports"  — JSON array of top-level public names (functions, classes, commands); [] if none
  "deps"     — JSON array of other dotfiles modules/scripts this file imports or calls;
               exclude stdlib and distro packages; [] if none

""" + FEW_SHOT_EXAMPLES


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def computeSha1(absPath):
    """Return hex SHA1 of file bytes."""
    h = hashlib.sha1()
    with open(absPath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def isBinary(absPath):
    """Heuristic: file is binary if it contains a NUL byte in the first 8KB."""
    try:
        with open(absPath, "rb") as f:
            return b"\x00" in f.read(BINARY_SNIFF_BYTES)
    except OSError:
        return False


def shouldSkip(relPath, absPath):
    """Return (skip: bool, reason: str)."""
    if relPath.startswith("index/") or relPath.startswith(".git/"):
        return True, "index or .git path"
    if SKIP_FILENAME_PATTERNS.search(relPath):
        return True, "lockfile or minified"
    try:
        size = os.path.getsize(absPath)
    except OSError:
        return True, "stat failed"
    if size > SKIP_SIZE_BYTES:
        return True, f"size {size} > 256KB"
    if isBinary(absPath):
        return True, "binary"
    return False, ""


def getFileSet():
    """Return list of repo-relative paths from git ls-files."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"git ls-files failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    return sorted(paths)


def verifyCtagsVariant():
    """
    Check ctags is installed and is the universal-ctags variant.
    Exits with an error message if not.
    """
    ctagsBin = None
    for candidate in ["ctags", "universal-ctags"]:
        result = subprocess.run(["which", candidate], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ctagsBin = result.stdout.strip()
            break

    if ctagsBin is None:
        print(
            "ERROR: ctags not found in PATH.\n"
            "Install universal-ctags (Arch: sudo pacman -S ctags) then retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    verResult = subprocess.run([ctagsBin, "--version"], capture_output=True, text=True, timeout=10)
    versionText = verResult.stdout + verResult.stderr
    if "Universal Ctags" not in versionText:
        print(
            f"ERROR: {ctagsBin} is NOT universal-ctags.\n"
            f"Version output:\n{versionText}\n"
            "Install universal-ctags (Arch: sudo pacman -S ctags) then retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    return ctagsBin


# ---------------------------------------------------------------------------
# TOML parser/writer (minimal — no dependency on third-party toml lib)
# ---------------------------------------------------------------------------

def _tomlStr(s):
    """Escape a string for TOML double-quoted value."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _tomlStrArray(lst):
    """Encode a list of strings as a TOML inline array."""
    return "[" + ", ".join(_tomlStr(x) for x in lst) + "]"


def serializeIndexToml(meta, entries):
    """
    Serialize index metadata and per-file entries to a TOML string.
    meta: dict with generatedAt, schemaVersion
    entries: list of (relPath, dict) sorted by relPath
    """
    lines = [
        "# Generated by Scripts/buildIndex.py — do not edit by hand.",
        "# Regenerate with: Scripts/buildIndex.py --full",
        f'generatedAt = "{meta["generatedAt"]}"',
        f'schemaVersion = {meta["schemaVersion"]}',
        "",
    ]
    for relPath, entry in entries:
        lines.append(f'[{_tomlStr(relPath)}]')
        lines.append(f'purpose = {_tomlStr(entry["purpose"])}')
        lines.append(f'tags = {_tomlStrArray(entry["tags"])}')
        lines.append(f'exports = {_tomlStrArray(entry["exports"])}')
        lines.append(f'deps = {_tomlStrArray(entry["deps"])}')
        lines.append(f'sha1 = "{entry["sha1"]}"')
        lines.append("")
    return "\n".join(lines)


def parseExistingIndex(tomlPath):
    """
    Minimal TOML parser that extracts only the sha1 fields we need for
    --changed-only diffing, plus carries forward all entry data.
    Returns dict: relPath -> entry dict (purpose, tags, exports, deps, sha1)
    """
    if not os.path.exists(tomlPath):
        return {}

    entries = {}
    currentKey = None
    currentEntry = {}

    with open(tomlPath, "r") as f:
        for rawLine in f:
            line = rawLine.strip()

            # Section header: ["some/path.lua"]
            m = re.match(r'^\[\"(.+)\"\]$', line)
            if m:
                if currentKey and currentEntry:
                    entries[currentKey] = currentEntry
                currentKey = m.group(1)
                currentEntry = {}
                continue

            if currentKey is None:
                continue

            # purpose = "..."
            mStr = re.match(r'^(\w+)\s*=\s*"(.*)"$', line)
            if mStr:
                field = mStr.group(1)
                val = mStr.group(2).replace('\\"', '"').replace("\\\\", "\\")
                currentEntry[field] = val
                continue

            # tags/exports/deps = ["a", "b"]
            mArr = re.match(r'^(\w+)\s*=\s*\[([^\]]*)\]', line)
            if mArr:
                field = mArr.group(1)
                rawItems = mArr.group(2)
                items = [x.strip().strip('"') for x in rawItems.split(",") if x.strip()]
                currentEntry[field] = items
                continue

    if currentKey and currentEntry:
        entries[currentKey] = currentEntry

    return entries


# ---------------------------------------------------------------------------
# ctags → SYMBOLS.tsv
# ---------------------------------------------------------------------------

def buildSymbolsTsv(keptFiles, ctagsBin, dryRun, verbose):
    """
    Run ctags over all kept files, filter to top-level symbols, write SYMBOLS.tsv.
    Returns list of TSV rows (dicts) for reporting.
    """
    if dryRun:
        print("[dry-run] would run ctags and write SYMBOLS.tsv", file=sys.stderr)
        return []

    absPaths = [os.path.join(REPO_ROOT, rp) for rp in keptFiles]

    if verbose:
        print(f"[ctags] running over {len(absPaths)} files...", file=sys.stderr)

    # Write file list to a temp file to avoid ARG_MAX issues
    listFile = os.path.join(INDEX_DIR, ".ctags_filelist.tmp")
    with open(listFile, "w") as f:
        f.write("\n".join(absPaths) + "\n")

    try:
        result = subprocess.run(
            [
                ctagsBin,
                "--output-format=u-ctags",
                "--fields=+nKZ",   # +n=line, +K=kind (long), +Z=scope
                "-L", listFile,
                "-f", "-",
            ],
            capture_output=True, text=True, timeout=120, cwd=REPO_ROOT
        )
    finally:
        try:
            os.remove(listFile)
        except OSError:
            pass

    if result.returncode != 0 and verbose:
        print(f"[ctags] stderr: {result.stderr[:500]}", file=sys.stderr)

    rows = []
    for line in result.stdout.splitlines():
        # Skip comment/metadata lines
        if line.startswith("!"):
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue

        symbol   = parts[0]
        absFile  = parts[1]
        # parts[2] is the ex-pattern, parts[3] onward are extension fields
        extFields = {}
        for part in parts[3:]:
            if ":" in part:
                k, _, v = part.partition(":")
                extFields[k.strip()] = v.strip()

        # Drop nested symbols (those with a scope field indicating enclosure)
        if "scope" in extFields:
            continue

        # Compute repo-relative path
        if absFile.startswith(REPO_ROOT + "/"):
            relFile = absFile[len(REPO_ROOT) + 1:]
        elif absFile.startswith(REPO_ROOT):
            relFile = absFile[len(REPO_ROOT):]
        else:
            relFile = absFile

        lineNo   = extFields.get("line", "0")
        kind     = extFields.get("kind", extFields.get("K", ""))
        language = extFields.get("language", "")

        rows.append({
            "symbol":   symbol,
            "file":     relFile,
            "line":     int(lineNo) if lineNo.isdigit() else 0,
            "kind":     kind,
            "language": language,
        })

    # Sort by file, then line
    rows.sort(key=lambda r: (r["file"], r["line"]))

    # Write TSV
    tsvLines = ["symbol\tfile\tline\tkind\tlanguage"]
    for r in rows:
        tsvLines.append(f"{r['symbol']}\t{r['file']}\t{r['line']}\t{r['kind']}\t{r['language']}")

    tsvContent = "\n".join(tsvLines) + "\n"
    tmpPath = SYMBOLS_TSV + ".tmp"
    with open(tmpPath, "w") as f:
        f.write(tsvContent)
    os.replace(tmpPath, SYMBOLS_TSV)

    if verbose:
        print(f"[ctags] wrote {len(rows)} top-level symbols to {SYMBOLS_TSV}", file=sys.stderr)

    return rows


# ---------------------------------------------------------------------------
# Qwen per-file analysis
# ---------------------------------------------------------------------------

def buildQwenPrompt(relPath, fileContents, truncated):
    """Construct the user prompt for a single file."""
    _, ext = os.path.splitext(relPath)
    langMap = {
        ".py": "Python", ".lua": "Lua", ".sh": "Shell", ".bash": "Shell",
        ".zsh": "Shell", ".js": "JavaScript", ".ts": "TypeScript",
        ".toml": "TOML", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".md": "Markdown", ".conf": "Config", ".ini": "INI",
        ".service": "systemd unit", ".txt": "Text",
    }
    language = langMap.get(ext.lower(), "unknown")

    truncNote = "\n[File truncated to first 12KB for analysis]" if truncated else ""
    tagList = ", ".join(LOCKED_TAGS)

    return (
        f"File path: {relPath}\n"
        f"Language: {language}\n"
        f"Locked tag vocabulary (use ONLY these): {tagList}\n"
        f"{truncNote}\n\n"
        f"<file>\n{fileContents}\n</file>\n\n"
        "Return a JSON object with fields: purpose, tags, exports, deps"
    )


def callQwen(session, relPath, absPath, verbose):
    """
    Call Qwen to analyse a file. Returns a dict with purpose/tags/exports/deps.
    Retries once on parse failure. Falls back to stub on second failure.
    """
    try:
        with open(absPath, "rb") as f:
            rawBytes = f.read(MAX_FILE_BYTES + 1)
        truncated = len(rawBytes) > MAX_FILE_BYTES
        contents = rawBytes[:MAX_FILE_BYTES].decode("utf-8", errors="replace")
    except OSError as e:
        print(f"[buildIndex] cannot read {relPath}: {e}", file=sys.stderr)
        return stubEntry(relPath, "read failed")

    prompt = buildQwenPrompt(relPath, contents, truncated)

    if verbose:
        print(f"[buildIndex] querying Qwen for {relPath}...", file=sys.stderr)

    for attempt in range(2):
        if attempt == 1:
            prompt = "Your previous response was not valid JSON. Try again.\n\n" + prompt

        raw = session.generate(prompt, system=SYSTEM_PROMPT, timeout=90, format="json")
        entry = parseQwenResponse(raw, relPath, verbose)
        if entry is not None:
            return entry

    print(f"[buildIndex] WARNING: Qwen parse failed twice for {relPath}, using stub", file=sys.stderr)
    return stubEntry(relPath, "TODO: indexing failed")


def parseQwenResponse(raw, relPath, verbose):
    """
    Parse Qwen JSON response. Returns dict or None on failure.
    Validates tags against locked vocabulary, retries unknown tags once.
    """
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Try stripping markdown fences
        cleaned = re.sub(r'```[^\n]*\n?', '', raw).strip()
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            if verbose:
                print(f"[buildIndex] JSON parse failed for {relPath}: {raw[:200]}", file=sys.stderr)
            return None

    if not isinstance(obj, dict):
        return None

    purpose  = str(obj.get("purpose", "")).strip()[:120] or "TODO: indexing failed"
    rawTags  = obj.get("tags", [])
    exports  = _normalizeStringList(obj.get("exports", []))
    deps     = _normalizeStringList(obj.get("deps", []))

    if isinstance(rawTags, str):
        rawTags = [t.strip() for t in rawTags.split(",") if t.strip()]
    elif not isinstance(rawTags, list):
        rawTags = []

    tags = [t.strip() for t in rawTags if isinstance(t, str) and t.strip() in LOCKED_TAG_SET]
    if len(tags) != len([t for t in rawTags if isinstance(t, str) and t.strip()]):
        unknownTags = [t for t in rawTags if isinstance(t, str) and t.strip() not in LOCKED_TAG_SET]
        if unknownTags:
            print(f"[buildIndex] WARNING: unknown tag(s) {unknownTags!r} for {relPath}", file=sys.stderr)
            # Return None to trigger retry on first attempt
            if tags:
                pass  # keep valid tags if we have some
            else:
                return None

    if not tags:
        tags = ["dotfile"]

    return {
        "purpose": purpose,
        "tags":    tags,
        "exports": exports,
        "deps":    deps,
    }


def _normalizeStringList(val):
    """Coerce a JSON value to a clean list of strings."""
    if isinstance(val, str):
        return [v.strip() for v in val.split(",") if v.strip()]
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    return []


def stubEntry(relPath, purpose):
    return {
        "purpose": purpose,
        "tags":    ["dotfile"],
        "exports": [],
        "deps":    [],
    }


# ---------------------------------------------------------------------------
# Main build logic
# ---------------------------------------------------------------------------

def runBuild(fullRebuild, dryRun, verbose):
    os.makedirs(INDEX_DIR, exist_ok=True)

    # 1. Verify ctags
    ctagsBin = verifyCtagsVariant()

    # 2. Get file set
    allFiles = getFileSet()
    if verbose:
        print(f"[buildIndex] {len(allFiles)} files from git ls-files", file=sys.stderr)

    # 3. Apply skip rules
    keptFiles   = []
    skippedFiles = []
    for relPath in allFiles:
        absPath = os.path.join(REPO_ROOT, relPath)
        skip, reason = shouldSkip(relPath, absPath)
        if skip:
            skippedFiles.append((relPath, reason))
            if verbose:
                print(f"[buildIndex] skipping {relPath}: {reason}", file=sys.stderr)
        else:
            keptFiles.append(relPath)

    print(f"[buildIndex] {len(keptFiles)} files to index, {len(skippedFiles)} skipped", file=sys.stderr)

    # 4. Load existing index for --changed-only
    existingEntries = {} if fullRebuild else parseExistingIndex(INDEX_TOML)

    # 5. Compute hashes and determine what needs Qwen
    fileHashes = {}
    needsQwen  = []
    carryOver  = {}

    for relPath in keptFiles:
        absPath = os.path.join(REPO_ROOT, relPath)
        sha1 = computeSha1(absPath)
        fileHashes[relPath] = sha1

        existing = existingEntries.get(relPath, {})
        if not fullRebuild and existing.get("sha1") == sha1:
            carryOver[relPath] = existing
        else:
            needsQwen.append(relPath)

    print(
        f"[buildIndex] {len(needsQwen)} files need Qwen, "
        f"{len(carryOver)} carried over from prior index",
        file=sys.stderr,
    )

    if dryRun:
        print("[dry-run] files that would be re-indexed:")
        for rp in needsQwen:
            print(f"  {rp}")
        print("[dry-run] would rebuild SYMBOLS.tsv")
        return

    # 6. Build SYMBOLS.tsv (always full rebuild, ctags is fast)
    buildSymbolsTsv(keptFiles, ctagsBin, dryRun=False, verbose=verbose)

    # 7. Call Qwen for changed files
    logger  = RingLogger(LOG_DIR)
    logData = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "fullRebuild": fullRebuild,
        "keptFiles":   len(keptFiles),
        "needsQwen":   needsQwen,
        "responses":   [],
    }

    newEntries = dict(carryOver)

    with ModelSession(DEFAULT_MODEL, verbose=verbose) as session:
        for i, relPath in enumerate(needsQwen):
            absPath = os.path.join(REPO_ROOT, relPath)
            if verbose:
                print(f"[buildIndex] [{i+1}/{len(needsQwen)}] {relPath}", file=sys.stderr)

            entry = callQwen(session, relPath, absPath, verbose)
            entry["sha1"] = fileHashes[relPath]
            newEntries[relPath] = entry

            logData["responses"].append({"path": relPath, "entry": entry})

    logger.write(logData)

    # 8. Write INDEX.toml atomically
    sortedEntries = sorted(newEntries.items(), key=lambda x: x[0])
    meta = {
        "generatedAt":  datetime.now(timezone.utc).isoformat(),
        "schemaVersion": 1,
    }
    tomlContent = serializeIndexToml(meta, sortedEntries)
    tmpPath = INDEX_TOML + ".tmp"
    with open(tmpPath, "w") as f:
        f.write(tomlContent)
    os.replace(tmpPath, INDEX_TOML)

    print(f"[buildIndex] wrote {len(sortedEntries)} entries to {INDEX_TOML}", file=sys.stderr)
    print(f"[buildIndex] done.", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build INDEX.toml and SYMBOLS.tsv for the dotfiles repo"
    )
    modeGroup = parser.add_mutually_exclusive_group()
    modeGroup.add_argument(
        "--full",
        action="store_true",
        help="Rebuild both index files from scratch (ignore existing hashes)",
    )
    modeGroup.add_argument(
        "--changed-only",
        dest="changedOnly",
        action="store_true",
        help="Re-run Qwen only for files whose SHA1 changed (default behavior)",
    )
    modeGroup.add_argument(
        "--dry-run",
        dest="dryRun",
        action="store_true",
        help="Print what would change, write nothing",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose debug output to stderr",
    )
    args = parser.parse_args()

    fullRebuild = args.full
    dryRun      = args.dryRun
    # default (no flag) → same as --changed-only
    runBuild(fullRebuild=fullRebuild, dryRun=dryRun, verbose=args.verbose)


if __name__ == "__main__":
    main()
