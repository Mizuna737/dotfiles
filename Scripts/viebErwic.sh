#!/usr/bin/env bash
# Wrapper around vieb for erwic instances. electron42 derives X11 WM_CLASS
# strictly from the bundled package.json's "name" field — it ignores
# `wmClassName`, `app.setName()`, and the `--name=` / `--class=` CLI flags
# for normal BrowserWindows. So we maintain one patched app.asar per erwic
# in ~/.cache/vieb-erwic/<name>/, repatched whenever the system asar updates.

set -euo pipefail

srcAsar="/usr/lib/vieb/app.asar"

# Find --erwic=PATH in args, peek at its "name", default to "vieb" if absent.
erwicFile=""
for arg in "$@"; do
  case "$arg" in --erwic=*) erwicFile="${arg#--erwic=}";; esac
done

erwicName="vieb"
if [[ -n "$erwicFile" && -f "$erwicFile" ]]; then
  erwicName="$(jq -r '.name // "vieb"' "$erwicFile" 2>/dev/null || echo vieb)"
  # Sanitize: only ASCII letters/digits/dash/underscore.
  erwicName="${erwicName//[^A-Za-z0-9_-]/_}"
  [[ -z "$erwicName" ]] && erwicName="vieb"
fi

cacheDir="$HOME/.cache/vieb-erwic/$erwicName"
patchedAsar="$cacheDir/app.asar"
stampFile="$cacheDir/.srcMtime"

srcMtime="$(stat -c %Y "$srcAsar")"
cachedMtime="$(cat "$stampFile" 2>/dev/null || echo 0)"

if [[ ! -f "$patchedAsar" ]] || [[ "$srcMtime" != "$cachedMtime" ]]; then
  echo "[viebErwic] building $erwicName asar..." >&2
  mkdir -p "$cacheDir"
  workDir="$(mktemp -d)"
  trap 'rm -rf "$workDir"' EXIT

  if command -v asar >/dev/null; then
    asarCmd=(asar)
  else
    asarCmd=(npx --yes @electron/asar)
  fi
  "${asarCmd[@]}" extract "$srcAsar" "$workDir/app"

  # Rewrite package.json "name" — that is what Electron uses for WM_CLASS.
  jq --arg n "$erwicName" '.name = $n' "$workDir/app/package.json" \
    >"$workDir/app/package.json.new"
  mv "$workDir/app/package.json.new" "$workDir/app/package.json"

  "${asarCmd[@]}" pack "$workDir/app" "$patchedAsar"
  echo "$srcMtime" >"$stampFile"
  echo "[viebErwic] cached at $patchedAsar (class=$erwicName)" >&2
fi

# Mirror the runtime env from /usr/bin/vieb so behavior matches stock vieb.
export ELECTRON_IS_DEV=0
export ELECTRON_FORCE_IS_PACKAGED=true
export ELECTRON_DISABLE_SECURITY_WARNINGS=true
export NODE_ENV=production
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export LD_LIBRARY_PATH="/usr/lib/vieb/lib:${LD_LIBRARY_PATH:-}"
export ELECTRON_OZONE_PLATFORM_HINT="${ELECTRON_OZONE_PLATFORM_HINT:-auto}"

cd /usr/lib/vieb
exec electron42 "$patchedAsar" "$@"
