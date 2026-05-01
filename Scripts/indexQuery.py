#!/usr/bin/env python3
"""indexQuery.py — Read-only query CLI over dotfiles INDEX.toml and SYMBOLS.tsv.

Subcommands:
  tags     TAG[,TAG...]   Files carrying any (or all) of the given tags
  file     PATH           Full entry for one file
  symbol   NAME           Symbol lookup in SYMBOLS.tsv
  search   QUERY          Substring match against purpose field
  deps     MODULE         Reverse-dep lookup by module name
  exports  TAG            All exported symbols from files with TAG
  stats                   Health-check summary of the index
"""

import argparse
import csv
import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent
INDEX_TOML  = REPO_ROOT / "index" / "INDEX.toml"
SYMBOLS_TSV = REPO_ROOT / "index" / "SYMBOLS.tsv"
SCRIPTS_DIR = Path(__file__).resolve().parent

MAX_RESULTS = 200
# Metadata keys present at the TOML top level that are NOT file entries
TOML_META_KEYS = {"generatedAt", "schemaVersion"}


# ---------------------------------------------------------------------------
# Import LOCKED_TAGS from buildIndex.py without running it
# ---------------------------------------------------------------------------
def _loadLockedTags() -> list[str]:
    """Parse LOCKED_TAGS from buildIndex.py at runtime to avoid duplication."""
    buildIndexPath = SCRIPTS_DIR / "buildIndex.py"
    if not buildIndexPath.exists():
        return []
    src = buildIndexPath.read_text()
    import re
    m = re.search(r'LOCKED_TAGS\s*=\s*\[(.*?)\]', src, re.DOTALL)
    if not m:
        return []
    items = re.findall(r'"([^"]+)"', m.group(1))
    return items


LOCKED_TAGS: list[str] = _loadLockedTags()
LOCKED_TAG_SET: set[str] = set(LOCKED_TAGS)


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------
def loadIndex() -> dict:
    """Load and return the parsed INDEX.toml as a dict, minus metadata keys."""
    if not INDEX_TOML.exists():
        _die(
            f"ERROR: {INDEX_TOML} not found.\n"
            "Run: Scripts/buildIndex.py --full"
        )
    with open(INDEX_TOML, "rb") as fh:
        raw = tomllib.load(fh)
    return {k: v for k, v in raw.items() if k not in TOML_META_KEYS}


def loadSymbols() -> list[dict]:
    """Load SYMBOLS.tsv into a list of row dicts."""
    if not SYMBOLS_TSV.exists():
        _die(
            f"ERROR: {SYMBOLS_TSV} not found.\n"
            "Run: Scripts/buildIndex.py --full"
        )
    rows = []
    with open(SYMBOLS_TSV, newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _tomlStr(s: str) -> str:
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _tomlStrArray(items: list) -> str:
    return "[" + ", ".join(_tomlStr(i) for i in items) + "]"


def formatTomlBlock(path: str, entry: dict) -> str:
    """Reconstruct a TOML block string from a parsed entry dict."""
    lines = [f'[{_tomlStr(path)}]' if any(c in path for c in ' #[]"\\') else f'[{path}]']
    lines.append(f'purpose = {_tomlStr(entry.get("purpose", ""))}')
    lines.append(f'tags = {_tomlStrArray(entry.get("tags", []))}')
    lines.append(f'exports = {_tomlStrArray(entry.get("exports", []))}')
    lines.append(f'deps = {_tomlStrArray(entry.get("deps", []))}')
    lines.append(f'sha1 = {_tomlStr(entry.get("sha1", ""))}')
    return "\n".join(lines)


def _die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _truncate(items: list, label: str = "results") -> list:
    if len(items) > MAX_RESULTS:
        print(f"WARNING: truncated to {MAX_RESULTS} {label}", file=sys.stderr)
        return items[:MAX_RESULTS]
    return items


def _normalizePath(rawPath: str) -> str:
    """Convert absolute or relative path to repo-relative string."""
    p = Path(rawPath)
    if p.is_absolute():
        try:
            return str(p.relative_to(REPO_ROOT))
        except ValueError:
            return rawPath
    return rawPath


# ---------------------------------------------------------------------------
# Subcommand: tags
# ---------------------------------------------------------------------------
def cmdTags(args, index: dict) -> int:
    rawTags = [t.strip() for t in ",".join(args.TAG).split(",") if t.strip()]
    unknown = [t for t in rawTags if t not in LOCKED_TAG_SET]
    if unknown:
        _die(
            f"ERROR: unknown tag(s): {', '.join(unknown)}\n"
            f"Valid tags: {', '.join(sorted(LOCKED_TAGS))}"
        )

    matched = []
    for path, entry in index.items():
        fileTags = set(entry.get("tags", []))
        if args.all:
            hit = all(t in fileTags for t in rawTags)
        else:
            hit = any(t in fileTags for t in rawTags)
        if hit:
            matched.append((path, entry))

    matched = _truncate(sorted(matched, key=lambda x: x[0]), "files")

    if not matched:
        print(f"no files found for tags: {', '.join(rawTags)}", file=sys.stderr)
        return 1

    if args.json:
        out = [{"path": p, "entry": e} for p, e in matched]
        print(json.dumps(out, indent=2))
    elif getattr(args, "full", False):
        for path, entry in matched:
            print(formatTomlBlock(path, entry))
            print()
    else:
        for path, _ in matched:
            print(path)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: file
# ---------------------------------------------------------------------------
def cmdFile(args, index: dict) -> int:
    target = _normalizePath(args.PATH)
    entry = index.get(target)

    if entry is None:
        # Suggest near-matches
        near = sorted(k for k in index if args.PATH in k or target in k)[:5]
        msg = f"ERROR: '{target}' not found in index."
        if near:
            msg += "\nNear-matches (try `search`):\n  " + "\n  ".join(near)
        _die(msg)

    if args.json:
        print(json.dumps({"path": target, "entry": entry}, indent=2))
    else:
        print(formatTomlBlock(target, entry))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: symbol
# ---------------------------------------------------------------------------
def cmdSymbol(args, index: dict) -> int:
    query = args.NAME
    rows = loadSymbols()

    matched = []
    for row in rows:
        sym = row.get("symbol", "")
        if args.exact:
            hit = sym == query
        else:
            hit = sym == query or sym.startswith(query)
        if hit:
            matched.append(row)

    if not matched:
        print(f"no matches for: {query}", file=sys.stderr)
        return 1

    matched = _truncate(
        sorted(matched, key=lambda r: (r.get("file", ""), r.get("symbol", ""))),
        "symbols"
    )

    if args.json:
        print(json.dumps(matched, indent=2))
    else:
        for row in matched:
            filePath = row.get("file", "")
            line     = row.get("line", "")
            sym      = row.get("symbol", "")
            kind     = row.get("kind", "")
            print(f"{filePath}:{line}\t{sym}\t{kind}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: search
# ---------------------------------------------------------------------------
def cmdSearch(args, index: dict) -> int:
    query = args.QUERY.lower()
    tagFilter = getattr(args, "tag", None)

    matched = []
    for path, entry in index.items():
        purpose = entry.get("purpose", "")
        if query not in purpose.lower():
            continue
        if tagFilter and tagFilter not in entry.get("tags", []):
            continue
        matched.append((path, purpose))

    if not matched:
        print(f"no matches for: {args.QUERY}", file=sys.stderr)
        return 1

    matched = _truncate(sorted(matched, key=lambda x: x[0]), "results")

    if args.json:
        out = [{"path": p, "purpose": pu} for p, pu in matched]
        print(json.dumps(out, indent=2))
    else:
        for path, purpose in matched:
            print(f"{path}\t{purpose}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: deps
# ---------------------------------------------------------------------------
def cmdDeps(args, index: dict) -> int:
    module = args.MODULE
    matched = sorted(
        path for path, entry in index.items()
        if module in entry.get("deps", [])
    )
    matched = _truncate(matched, "files")

    if not matched:
        print(f"no files depend on: {module}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(matched, indent=2))
    else:
        for path in matched:
            print(path)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: exports
# ---------------------------------------------------------------------------
def cmdExports(args, index: dict) -> int:
    tag = args.TAG
    if tag not in LOCKED_TAG_SET:
        _die(
            f"ERROR: unknown tag: {tag}\n"
            f"Valid tags: {', '.join(sorted(LOCKED_TAGS))}"
        )

    rows = []
    for path, entry in index.items():
        if tag not in entry.get("tags", []):
            continue
        for sym in entry.get("exports", []):
            rows.append((path, sym))

    rows = _truncate(sorted(rows, key=lambda x: (x[0], x[1])), "symbols")

    if not rows:
        print(f"no exports found for tag: {tag}", file=sys.stderr)
        return 1

    if args.json:
        out = [{"path": p, "symbol": s} for p, s in rows]
        print(json.dumps(out, indent=2))
    else:
        for path, sym in rows:
            print(f"{path}\t{sym}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: stats
# ---------------------------------------------------------------------------
def cmdStats(args, index: dict) -> int:
    totalFiles = len(index)
    tagCounts: dict[str, int] = {}
    emptyExports = 0
    failedPurpose = 0

    for entry in index.values():
        for t in entry.get("tags", []):
            tagCounts[t] = tagCounts.get(t, 0) + 1
        if not entry.get("exports"):
            emptyExports += 1
        if entry.get("purpose", "") == "TODO: indexing failed":
            failedPurpose += 1

    if args.json:
        print(json.dumps({
            "totalFiles": totalFiles,
            "tagCounts": dict(sorted(tagCounts.items(), key=lambda x: -x[1])),
            "emptyExports": emptyExports,
            "failedPurpose": failedPurpose,
        }, indent=2))
    else:
        print(f"total files:        {totalFiles}")
        print(f"empty exports:      {emptyExports}")
        print(f"indexing failures:  {failedPurpose}")
        print()
        print("files per tag:")
        for tag, count in sorted(tagCounts.items(), key=lambda x: -x[1]):
            print(f"  {tag:<18} {count}")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="indexQuery.py",
        description="Read-only query CLI over dotfiles INDEX.toml and SYMBOLS.tsv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Global flags --json and --full work on subcommands that support them.\n\n"
            "Examples:\n"
            "  indexQuery.py tags awesome\n"
            "  indexQuery.py tags awesome,dashboard --all\n"
            "  indexQuery.py file .config/awesome/bar.lua\n"
            "  indexQuery.py symbol toggleDropdown\n"
            "  indexQuery.py symbol updateVolumeWidget --exact\n"
            "  indexQuery.py search 'workspace manager'\n"
            "  indexQuery.py search wibar --tag awesome\n"
            "  indexQuery.py deps awful\n"
            "  indexQuery.py exports awesome\n"
            "  indexQuery.py stats\n"
            "  indexQuery.py stats --json\n"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")

    sub = parser.add_subparsers(dest="cmd", metavar="SUBCOMMAND")
    sub.required = True

    # tags
    pTags = sub.add_parser(
        "tags",
        help="Files carrying given tag(s). Example: indexQuery.py tags awesome,dashboard",
    )
    pTags.add_argument("TAG", nargs="+", help="Tag(s) — comma-separated or space-separated")
    pTags.add_argument("--all", action="store_true", help="AND semantics (all tags must match)")
    pTags.add_argument("--full", action="store_true", help="Emit full TOML block per file")

    # file
    pFile = sub.add_parser(
        "file",
        help="Full entry for one file. Example: indexQuery.py file .config/awesome/bar.lua",
    )
    pFile.add_argument("PATH", help="Repo-relative or absolute path")

    # symbol
    pSymbol = sub.add_parser(
        "symbol",
        help="Symbol lookup. Example: indexQuery.py symbol toggleDropdown",
    )
    pSymbol.add_argument("NAME", help="Symbol name (prefix match by default)")
    pSymbol.add_argument("--exact", action="store_true", help="Exact match only")

    # search
    pSearch = sub.add_parser(
        "search",
        help="Substring match on purpose field. Example: indexQuery.py search 'workspace'",
    )
    pSearch.add_argument("QUERY", help="Case-insensitive substring")
    pSearch.add_argument("--tag", metavar="TAG", help="Constrain to files with this tag")

    # deps
    pDeps = sub.add_parser(
        "deps",
        help="Reverse-dep lookup. Example: indexQuery.py deps awful",
    )
    pDeps.add_argument("MODULE", help="Module/dep name (exact string match)")

    # exports
    pExports = sub.add_parser(
        "exports",
        help="All exports from files with TAG. Example: indexQuery.py exports awesome",
    )
    pExports.add_argument("TAG", help="Tag name")

    # stats
    sub.add_parser(
        "stats",
        help="Index health summary. Example: indexQuery.py stats",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = buildParser()
    args = parser.parse_args()

    # Load index once; symbols are loaded lazily by subcommands that need them
    index = loadIndex()

    dispatch = {
        "tags":    cmdTags,
        "file":    cmdFile,
        "symbol":  cmdSymbol,
        "search":  cmdSearch,
        "deps":    cmdDeps,
        "exports": cmdExports,
        "stats":   cmdStats,
    }

    handler = dispatch.get(args.cmd)
    if handler is None:
        _die(f"ERROR: unknown subcommand: {args.cmd}")

    return handler(args, index)


if __name__ == "__main__":
    sys.exit(main())
