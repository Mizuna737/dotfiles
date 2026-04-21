"""localModel.py — shared Ollama session, TOON codec, and ring logger."""

import os
import re
import sys
import json
import time
import subprocess

import requests

DEFAULT_MODEL = "qwen2.5-coder:7b-instruct-q4_K_M"
DEFAULT_HOST  = "http://localhost:11434"

# ---------------------------------------------------------------------------
# TOON codec
# Uniform arrays of flat objects. Header: name[N]{f1,f2,...}:\n then N rows.
# Values containing spaces, quotes, backslashes, or [],:{}  are double-quoted
# with inner " and \ backslash-escaped.
# ---------------------------------------------------------------------------

_TOON_NEEDS_QUOTE = re.compile(r'[\s\[\],:{}"\\]')


def _toonEscape(val):
    s = str(val)
    if not s or _TOON_NEEDS_QUOTE.search(s):
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'
    return s


def toonEncode(name, rows, fields=None):
    """
    Encode list-of-dicts to TOON block string.
    If fields is None, keys are inferred from the first row.
    """
    if fields is None:
        fields = list(rows[0].keys()) if rows else []
    header = f"{name}[{len(rows)}]{{{','.join(fields)}}}:"
    lines = [header]
    for row in rows:
        lines.append(" ".join(_toonEscape(row.get(f, "")) for f in fields))
    return "\n".join(lines)


def _toonParseLine(line):
    """Split a TOON data row into values, respecting quoted strings."""
    values = []
    i = 0
    while i < len(line):
        if line[i] == ' ':
            i += 1
            continue
        if line[i] == '"':
            # Quoted value: scan for closing unescaped quote
            i += 1
            buf = []
            while i < len(line):
                c = line[i]
                if c == '\\' and i + 1 < len(line):
                    buf.append(line[i + 1])
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
            values.append("".join(buf))
        else:
            # Unquoted: read until space
            j = i
            while j < len(line) and line[j] != ' ':
                j += 1
            values.append(line[i:j])
            i = j
    return values


def toonDecode(text):
    """
    Decode first TOON block found in text.
    Strips markdown fences before parsing.
    Returns (name, list-of-dicts) or raises ValueError.

    Also handles a degenerate form the model sometimes emits:
      picks[N]{v1,v2,...}: — indices stuffed into the field list instead of rows.
    """
    # Strip markdown code fences the model sometimes wraps around output
    text = re.sub(r'```[^\n]*\n?', '', text).strip()
    headerRe = re.compile(r'(\w+)\[(\d+)\]\{([^}]*)\}:?')
    m = headerRe.search(text)
    if not m:
        raise ValueError("No TOON header found")
    name  = m.group(1)
    count = int(m.group(2))
    rawFields = [f.strip() for f in m.group(3).split(",")]

    # Degenerate: model put values in the field list (e.g. picks[8]{1,2,21,32})
    if all(f.lstrip('-').isdigit() for f in rawFields if f):
        rows = [{"i": f} for f in rawFields if f]
        return name, rows

    fields = rawFields
    rest = text[m.end():]
    rawLines = []
    for l in rest.splitlines():
        stripped = l.strip()
        if not stripped:
            continue
        rawLines.append(stripped)
        if len(rawLines) >= max(count, 1):
            break

    rows = []
    for line in rawLines:
        values = _toonParseLine(line.strip())
        row = {}
        for i, field in enumerate(fields):
            row[field] = values[i] if i < len(values) else ""
        rows.append(row)
    return name, rows


# ---------------------------------------------------------------------------
# ModelSession
# ---------------------------------------------------------------------------

class ModelSession:
    """
    Context manager: keeps model resident during job, unloads on exit.

    Usage:
        with ModelSession() as sess:
            reply = sess.generate(prompt, system="You are ...")
    """

    def __init__(self, model=DEFAULT_MODEL, host=DEFAULT_HOST, verbose=False):
        self.model   = model
        self.host    = host
        self.verbose = verbose
        self._url    = host.rstrip("/") + "/api/generate"

    def __enter__(self):
        if self.verbose:
            print(f"[ModelSession] using {self.model} @ {self.host}", file=sys.stderr)
        return self

    def __exit__(self, *_):
        # keep_alive=0 tells Ollama to evict the model from VRAM immediately
        try:
            requests.post(self._url, json={
                "model": self.model,
                "prompt": "",
                "keep_alive": 0,
                "stream": False,
            }, timeout=10)
            if self.verbose:
                print(f"[ModelSession] unloaded {self.model}", file=sys.stderr)
        except Exception as e:
            if self.verbose:
                print(f"[ModelSession] unload warning: {e}", file=sys.stderr)
            # Fallback: subprocess ollama stop
            try:
                subprocess.run(["ollama", "stop", self.model], timeout=5, capture_output=True)
            except Exception:
                pass

    def generate(self, prompt, system=None, timeout=60, format=None):
        """
        POST to /api/generate with keep_alive="5m" so the model stays loaded
        between calls in the same session. Retries once on connection error.
        Pass format="json" to force structured JSON output.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": 0.1},
        }
        if system is not None:
            payload["system"] = system
        if format is not None:
            payload["format"] = format

        for attempt in range(2):
            try:
                resp = requests.post(self._url, json=payload, timeout=timeout)
                if resp.status_code == 404:
                    print(
                        f"Model not found. Pull it with:\n  ollama pull {self.model}",
                        file=sys.stderr,
                    )
                    sys.exit(3)
                resp.raise_for_status()
                return resp.json()["response"].strip()
            except requests.exceptions.ConnectionError as e:
                if attempt == 0:
                    if self.verbose:
                        print(f"[ModelSession] retry after connection error: {e}", file=sys.stderr)
                    continue
                print(f"Ollama unreachable at {self._url}: {e}", file=sys.stderr)
                sys.exit(2)
            except requests.exceptions.Timeout:
                print(f"Model call timed out after {timeout}s", file=sys.stderr)
                sys.exit(2)
            except requests.exceptions.HTTPError as e:
                print(f"HTTP error from Ollama: {e}", file=sys.stderr)
                sys.exit(2)


# ---------------------------------------------------------------------------
# RingLogger
# ---------------------------------------------------------------------------

class RingLogger:
    """
    Writes run_<unixts>_<pid>.json files into logDir and prunes all but the
    newest `keep` matching run_*.json files.
    """

    def __init__(self, logDir, keep=5):
        self.logDir = logDir
        self.keep   = keep

    def write(self, payload: dict) -> str:
        os.makedirs(self.logDir, exist_ok=True)
        ts  = int(time.time())
        pid = os.getpid()
        path = os.path.join(self.logDir, f"run_{ts}_{pid}.json")
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        self._prune()
        return path

    def _prune(self):
        try:
            files = [
                os.path.join(self.logDir, f)
                for f in os.listdir(self.logDir)
                if f.startswith("run_") and f.endswith(".json")
            ]
            files.sort(key=os.path.getmtime, reverse=True)
            for old in files[self.keep:]:
                os.remove(old)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------

def selftest():
    """Round-trip a sample object list through TOON encode/decode."""
    sample = [
        {"i": "0", "path": "/home/max/dotfiles/Scripts/foo.py"},
        {"i": "1", "path": "/path/with spaces/bar.lua"},
        {"i": "2", "path": 'quote"test\\baz.sh'},
    ]
    encoded = toonEncode("files", sample, ["i", "path"])
    print("Encoded:\n" + encoded)
    _, decoded = toonDecode(encoded)
    assert decoded == sample, f"Mismatch:\n  expected {sample}\n  got {decoded}"

    hits = [{"startLine": "10", "endLine": "25", "reason": "toggle logic here"}]
    enc2 = toonEncode("hits", hits, ["startLine", "endLine", "reason"])
    _, dec2 = toonDecode(enc2)
    assert dec2 == hits, f"Hits mismatch: {dec2}"

    print("TOON selftest passed.")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    print("Usage: python3 localModel.py --selftest")
