#!/usr/bin/env python3
"""draftCommit.py — Draft a git commit message with noise filtering and diff grouping.

Groups changed files by component, filters noise (themes, bak, locks, quickmarks,
uploads, browser history), and sends a structured diff summary to the local Qwen
model for conventional commit message generation.

Usage:
  python3 draftCommit.py --staged          # draft from staged diff
  python3 draftCommit.py --all             # draft from all unstaged + staged
  python3 draftCommit.py --dry             # print grouped diff + TOON only
  python3 draftCommit.py --staged --toonly # TOON summary only
  python3 draftCommit.py --help            # show usage
"""

import sys
import os
import re
import argparse
import subprocess
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib.localModel import ModelSession

# ---------------------------------------------------------------------------
# Noise patterns — files to skip entirely
# ---------------------------------------------------------------------------

NOISE_PATTERNS = [
    r'\.bak$',
    r'\.lock$',
    r'wall-uploads/',
    r'chat_auth_secret$',
    r'chat_admin_setup$',
    r'chat_users\.db$',
    r'wall-layout\.json$',
    r'quickmarks$',
    r'.*/bookmarks',
]

NOISE_COMPILED = [re.compile(p) for p in NOISE_PATTERNS]


def is_noise(path):
    for pattern in NOISE_COMPILED:
        if pattern.search(path):
            return True
    return False


def filter_paths(paths):
    return [p for p in paths if not is_noise(p)]

# ---------------------------------------------------------------------------
# Component grouping
# ---------------------------------------------------------------------------

COMPONENT_ORDER = [
    ("awesome", ".config/awesome"),
    ("dashboard", ".config/dashboard"),
    ("scripts", "Scripts/"),
    ("config", ".config/"),
    ("dotfiles", None),
    ("packages", "packages/"),
]


def group_by_component(paths):
    groups = {}
    uncategorized = []
    for path in paths:
        placed = False
        for comp, prefix in COMPONENT_ORDER:
            if prefix and path.startswith(prefix):
                groups.setdefault(comp, []).append(path)
                placed = True
                break
        if not placed:
            uncategorized.append(path)
    if uncategorized:
        groups["misc"] = uncategorized

    result = []
    for comp, _ in COMPONENT_ORDER:
        if comp in groups:
            result.append((comp, sorted(groups[comp])))
    if "misc" in groups:
        result.append(("misc", sorted(groups["misc"])))
    return result

# ---------------------------------------------------------------------------
# Diff builder
# ---------------------------------------------------------------------------

def get_diff_text(staged=False, range_spec=None, root=None):
    if range_spec:
        cmd = ["git", "diff", range_spec]
    elif staged:
        cmd = ["git", "diff", "--staged"]
    else:
        cmd = ["git", "diff"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                            cwd=root or os.getcwd())
    return result.stdout


def get_tracked_diff_with_filter(root=None):
    repo_root = root or os.getcwd()
    result = subprocess.run(
        ["git", "diff", "--name-only", "--cached"],
        capture_output=True, text=True, timeout=30, cwd=repo_root,
    )
    if not result.stdout.strip():
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, timeout=30, cwd=repo_root,
        )

    all_files = [f for f in result.stdout.strip().splitlines() if f]

    if not all_files:
        result = subprocess.run(
            ["git", "ls-files", "--modified", "--deleted",
             "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30, cwd=repo_root,
        )
        all_files = [f for f in result.stdout.strip().splitlines() if f]

    full_diff = get_diff_text(staged=False, root=repo_root)
    filtered_lines = []
    filtered_files = set()
    current_file = None

    for line in full_diff.split('\n'):
        m = re.match(r'^diff --git a/(.+) b/(.+)$', line)
        if m:
            current_file = m.group(1)
            if is_noise(current_file):
                filtered_files.add(current_file)
                continue
            filtered_lines.append(line)
        elif current_file and is_noise(current_file) and line.startswith('diff --'):
            current_file = line.split(' b/')[-1] if ' b/' in line else None
            if is_noise(current_file):
                filtered_files.add(current_file)
                continue
            filtered_lines.append(line)
        else:
            filtered_lines.append(line)

    filtered_diff = '\n'.join(filtered_lines)

    if not filtered_diff.strip():
        result = subprocess.run(
            ["git", "ls-files", "--modified", "--deleted",
             "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30, cwd=repo_root,
        )
        untracked = [f for f in result.stdout.strip().splitlines() if f]
        untracked = filter_paths(untracked)

        result2 = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, timeout=30, cwd=repo_root,
        )
        tracked = [f for f in result2.stdout.strip().splitlines() if f]
        tracked = filter_paths(tracked)

        all_files = sorted(set(untracked + tracked))
        if all_files:
            filtered_files = set(all_files)

    return filtered_diff, filtered_files

# ---------------------------------------------------------------------------
# Commit message generation
# ---------------------------------------------------------------------------

COMMIT_SYSTEM = """\
You are a git commit message writer for a Linux power user's dotfiles repo.

## Commit message format
Line 1: `<type>: <imperative summary>`, ≤72 characters
Line 2: blank
Lines 3+: bullet points (2-4, each "- ") describing WHAT changed and WHY.

## Type convention
- `feat` — new capability, new keybinding, new config area, new script feature
- `fix` — repair something broken
- `refactor` — restructure without behavior change
- `chore` — package updates, path migrations, housekeeping
- `test` — add/modify tests

## What to INCLUDE
- New features/capabilities with their key details
- New keybindings and their triggers
- Bug fixes describing what was broken
- Cross-cutting changes (e.g. "migrate vault path across 6 scripts") in ONE bullet
- Package additions listed together: "add packages: x, y, z"

## What to EXCLUDE
- Auto-generated output (chooseWallpaper theme updates, .bak files)
- Browser bookmarks/quickmarks/history (zen, qute, vieb)
- Secrets, auth files, uploaded images
- Lock files, cache files
- Every file individually — group by logical area
- Single-line path fixes across many scripts (summarize as one bullet)

## Grouping
- Files in the same area → one bullet
- Keybindings across device configs → one bullet
- Path changes across scripts → one bullet

## Rules
- Use imperative mood ("add", not "added")
- Each bullet starts with a verb: add, fix, update, rename, migrate, remove
- Keep bullets concise but descriptive
- Output ONLY the commit message — no markdown, no explanation, no headers"""


def generate_commit_message(grouped, diff_text, root=None):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:8080")
    model = os.environ.get("COMMIT_MODEL", "Qwen3.6-35B-A3B-UD-Q6_K.gguf")

    lines = []
    if diff_text.strip():
        lines.append("=== Grouped diff ===")
        for comp, files in grouped:
            lines.append(f"\n[{comp}]")
            for f in files:
                lines.append(f"  {f}")
        lines.append("")
        lines.append("=== Diff content ===")
        lines.append(diff_text[:12000])
        if len(diff_text) > 12000:
            lines.append("[diff truncated — see file list above for scope]")
    else:
        lines.append("=== Grouped changes ===")
        for comp, files in grouped:
            lines.append(f"\n[{comp}]")
            for f in files:
                lines.append(f"  {f}")

    user_prompt = "\n".join(lines)

    with ModelSession(model, host=host) as session:
        response = session.generate(user_prompt, system=COMMIT_SYSTEM, timeout=120)

    response = response.strip()
    response = re.sub(r'^```[^\n]*\n?', '', response).strip()
    response = re.sub(r'\n?```$', '', response).strip()

    resp_lines = response.splitlines()
    title = resp_lines[0].strip() if resp_lines else ""
    body_lines = []
    i = 1
    while i < len(resp_lines) and not resp_lines[i].strip():
        i += 1
    if i < len(resp_lines):
        body_lines = resp_lines[i:]

    return title, "\n".join(body_lines).strip() if body_lines else ""

# ---------------------------------------------------------------------------
# TOON output
# ---------------------------------------------------------------------------

def _toon_escape(val):
    s = str(val)
    if not s or re.search(r'[\s\[\],:{}"\\]', s):
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'
    return s


def toon_encode_changes(comp_groups, diff_groups):
    rows = []
    for comp, files in comp_groups:
        for f in files:
            rows.append({"comp": comp, "file": f, "kind": "feat", "reason": ""})

    if not rows:
        return ""

    header = f"changes[{len(rows)}]{{comp,file,kind,reason}}:"
    for row in rows:
        vals = [_toon_escape(row[c]) for c in ("comp", "file", "kind", "reason")]
        header += "\n" + " ".join(vals)
    return header

# ---------------------------------------------------------------------------
# Secret scanning
# ---------------------------------------------------------------------------

SECRET_SCAN_SYSTEM = """\
You are a security scanner. Inspect the following code/diff for secrets.

Look for: SSH private keys, API tokens, passwords, .env values, bearer tokens, \
AWS/GCP/Azure credentials, database connection strings, private certificates, \
hardcoded credentials of any kind.

Bias toward flagging — a false positive is better than a false negative.

If you find NOTHING suspicious, output exactly:
CLEAN

If you find anything suspicious, output exactly:
SECRETS_FOUND
- <file or location>: <one-line description>
(one bullet per finding, no other text before or after)"""


def secret_scan_diff(diff_text):
    if not diff_text.strip():
        return True

    blob = diff_text[:20000]
    if len(diff_text) > 20000:
        blob += "\n[truncated]"

    host = os.environ.get("OLLAMA_HOST", "http://localhost:8080")
    model = os.environ.get("COMMIT_MODEL", "Qwen3.6-35B-A3B-UD-Q6_K.gguf")

    with ModelSession(model, host=host) as session:
        result = session.generate(
            f"Content to scan:\n```\n{blob}\n```\n\nReport now.",
            system=SECRET_SCAN_SYSTEM,
            timeout=90,
        )

    first_line = result.strip().splitlines()[0].strip() if result.strip() else ""
    if first_line == "SECRETS_FOUND":
        print(f"\n=== SECRET SCAN ALERT ===", file=sys.stderr)
        print(result.strip(), file=sys.stderr)
        print("\nAbort — nothing staged or committed.", file=sys.stderr)
        sys.exit(1)
    return True

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Draft a git commit message with noise filtering and diff grouping.",
        epilog="Examples:\n"
               "  python3 draftCommit.py --staged\n"
               "  python3 draftCommit.py --all\n"
               "  python3 draftCommit.py --dry --staged\n"
               "  python3 draftCommit.py --staged --toonly\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true",
                       help="Use git diff --staged")
    group.add_argument("--all", action="store_true",
                       help="Use all changes (staged + unstaged)")
    group.add_argument("--range", metavar="REF..REF",
                       help="Use git diff <range>")
    parser.add_argument("--dry", action="store_true",
                        help="Show grouped diff + TOON only, no commit message")
    parser.add_argument("--toonly", action="store_true",
                        help="TOON summary only")
    parser.add_argument("--model", default=None,
                        help="Override model name")
    parser.add_argument("--root", default=os.getcwd(),
                        help="Git repo root")
    args = parser.parse_args()

    repo_root = args.root

    if args.range:
        diff_text = get_diff_text(range_spec=args.range, root=repo_root)
    elif args.staged or args.all:
        diff_text = get_diff_text(staged=args.staged, root=repo_root)
    else:
        diff_text = get_diff_text(staged=False, root=repo_root)

    _, filtered_files = get_tracked_diff_with_filter(root=repo_root)
    filtered_files = filter_paths(list(filtered_files))

    if not filtered_files:
        print("No tracked changes to commit (all noise or empty diff).")
        sys.exit(0)

    grouped = group_by_component(filtered_files)

    if args.toonly:
        print(toon_encode_changes(grouped, {}))
        sys.exit(0)

    if args.dry:
        print("=== Grouped changes ===")
        for comp, files in grouped:
            print(f"\n[{comp}]")
            for f in files:
                print(f"  {f}")
        print()
        print("=== TOON summary ===")
        print(toon_encode_changes(grouped, {}))
        print("=== Done ===")
        sys.exit(0)

    title, body = generate_commit_message(grouped, diff_text, root=repo_root)

    print()
    print("=" * 56)
    print(f"  Title: {title}")
    print("=" * 56)
    if body:
        print()
        for line in body.split('\n'):
            print(f"  {line}")
    print("=" * 56)
    print()
    print("(edit to accept, or Ctrl-C to abort)")

    tmp = f"/tmp/draft_commit_{os.getpid()}.txt"
    with open(tmp, "w") as f:
        f.write(title + "\n\n" + (body or ""))

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, tmp])

    with open(tmp, "r") as f:
        content = f.read().strip()
    os.remove(tmp)

    lines = content.splitlines()
    new_title = lines[0].strip() if lines else title
    new_body = "\n".join(lines[2:]).strip() if len(lines) > 2 else body

    print(f"\nCommitted: {new_title}")
    subprocess.run(["git", "commit", "-m", new_title, "-m", new_body],
                   cwd=repo_root)

    print()
    resp = input("push now? [Y/n]: ").strip().lower()
    if resp not in ("n", "no"):
        subprocess.run(["git", "push"], cwd=repo_root)


if __name__ == "__main__":
    main()
