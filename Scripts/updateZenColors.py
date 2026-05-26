#!/usr/bin/env python3
"""Regenerate Zen Browser userChrome.css from pywal colors.

Reads ~/.cache/wal/colors.json + Scripts/zenChrome.css.template,
substitutes {{color0..color15}} placeholders, writes to the Zen profile's
chrome/userChrome.css. The fx-autoconfig pywalReload.uc.js watcher picks up
the mtime change and live-reloads the sheet (~1s).

Run after pywal regen, or wire into chooseWallpaper.sh.
"""

import json
import re
import sys
from pathlib import Path

COLORS_JSON = Path.home() / ".cache/wal/colors.json"
TEMPLATE = Path(__file__).parent / "zenChrome.css.template"
ZEN_PROFILE_GLOB = "*.max"  # matches scvx2p89.max etc.
ZEN_DIR = Path.home() / ".zen"


def findProfileDir() -> Path:
    matches = sorted(ZEN_DIR.glob(ZEN_PROFILE_GLOB))
    if not matches:
        sys.exit(f"no Zen profile matching {ZEN_PROFILE_GLOB} under {ZEN_DIR}")
    if len(matches) > 1:
        print(f"warning: multiple profiles matched, using {matches[0].name}", file=sys.stderr)
    return matches[0]


def main() -> int:
    if not COLORS_JSON.exists():
        sys.exit(f"missing {COLORS_JSON} — run pywal first")
    if not TEMPLATE.exists():
        sys.exit(f"missing template {TEMPLATE}")

    colors = json.loads(COLORS_JSON.read_text())["colors"]
    text = TEMPLATE.read_text()
    text = re.sub(r"\{\{(color\d+)\}\}", lambda m: colors[m.group(1)], text)

    # Write to chrome/pywal.css. The pywalReload.uc.js watcher registers this
    # sheet via nsIStyleSheetService as a data: URI and re-registers on mtime
    # change — bypasses both Firefox's native userChrome.css loader (no live
    # reload) and fx-autoconfig's CSS/ manager (no loader access from scripts).
    out = findProfileDir() / "chrome/pywal.css"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out} (color6={colors['color6']} color3={colors['color3']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
