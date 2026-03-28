#!/usr/bin/env python3
"""
dashboard-server.py
Thin HTTP bridge for the AwesomeWM dashboard.
Runs on localhost:9876, handles:
  GET  /status/toggles  → VPN + audio sink state
  GET  /status/media    → playerctl metadata
  GET  /status/tasks    → today's Obsidian tasks
  POST /toggle/vpn      → toggle Windscribe VPN
  POST /toggle/sink     → cycle PulseAudio/Pipewire sink
  POST /media/<cmd>     → playerctl commands
"""

import json
import subprocess
import re
import os
import glob
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import urlparse
import threading
import queue
import gi
gi.require_version("GLib", "2.0")

OBSIDIAN_VAULT = os.path.expanduser("~/Documents/The Vault")
PORT = 9876

# ── Helpers ────────────────────────────────────────────────────────────────

def run(cmd, timeout=4):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except Exception:
        return "", 1

def jsonResp(handler, data, status=200):
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", len(body))
    handler.end_headers()
    handler.wfile.write(body)

# ── VPN ───────────────────────────────────────────────────────────────────

def getVpnState():
    out, _ = run(["windscribe-cli", "status"])
    active = False
    label = ""
    for line in out.splitlines():
        if line.startswith("{"):
            continue  # skip JSON log lines
        lower = line.lower()
        if "connect state:" in lower:
            # "Connect state: Connected: Seattle - Cobain"
            # "Connect state: Disconnected"
            active = "connected:" in lower  # "connected:" excludes "disconnected"
            parts = line.split(":", 2)
            label = parts[2].strip() if len(parts) >= 3 else ""
    return {"active": active, "label": label}

def toggleVpn():
    state = getVpnState()
    if state["active"]:
        run(["windscribe-cli", "disconnect"])
    else:
        # Connect to best location; change "best" to a specific location if preferred
        run(["windscribe-cli", "connect", "best"])
    # Push updated VPN state (slight delay to let windscribe-cli settle)
    import time; time.sleep(1)
    sseBroadcast("vpn-changed", getVpnState())

# ── Audio Sink ────────────────────────────────────────────────────────────

# Friendly display names for known sinks
SINK_NAMES = {
    "alsa_output.usb-Burr-Brown_from_TI_USB_Audio_CODEC-00.analog-stereo-output": "Headphones",
    "alsa_output.pci-0000_2d_00.4.analog-stereo": "Speakers",
}

def getSinks():
    out, _ = run(["pactl", "list", "short", "sinks"])
    sinks = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sinks.append({"id": parts[0], "name": parts[1]})
    return sinks

def getDefaultSink():
    out, _ = run(["pactl", "get-default-sink"])
    return out.strip()

def cycleSink():
    # Only cycle between known named sinks
    allowedSinks = list(SINK_NAMES.keys())
    current = getDefaultSink()
    try:
        idx = allowedSinks.index(current)
    except ValueError:
        idx = 0
    nextSink = allowedSinks[(idx + 1) % len(allowedSinks)]
    run(["pactl", "set-default-sink", nextSink])
    # Move all active streams to the new sink
    streamsOut, _ = run(["pactl", "list", "short", "sink-inputs"])
    for line in streamsOut.splitlines():
        parts = line.split()
        if parts:
            run(["pactl", "move-sink-input", parts[0], nextSink])
    # Push updated state to all SSE clients immediately
    sseBroadcast("sink-changed", getSinkState())

def getSinkState():
    current = getDefaultSink()
    label = SINK_NAMES.get(current, current.split(".")[-1])
    return {"active": True, "label": label, "sink": current}

# ── Media (playerctl) ─────────────────────────────────────────────────────

def getMediaState():
    status, code = run(["playerctl", "status"])
    if code != 0 or status in ("No players found", ""):
        return {}

    metaOut, _ = run(["playerctl", "metadata", "--format",
        "{{xesam:title}}|{{xesam:artist}}|{{xesam:album}}"])
    lines = metaOut.split("|")
    title  = lines[0] if len(lines) > 0 else ""
    artist = lines[1] if len(lines) > 1 else ""
    album  = lines[2] if len(lines) > 2 else ""

    rawPos, _ = run(["playerctl", "position"])
    try:
        posF = float(rawPos)
    except Exception:
        posF = 0

    rawLen, _ = run(["playerctl", "metadata", "mpris:length"])
    try:
        lenF = int(rawLen) / 1e6
    except Exception:
        lenF = 0

    return {
        "status": status,
        "title":  title,
        "artist": artist,
        "album":  album,
        "position": posF,
        "length":   lenF,
    }

def mediaCommand(cmd):
    validCmds = {"play", "pause", "play-pause", "next", "previous", "stop"}
    if cmd in validCmds:
        run(["playerctl", cmd])

# ── Tasks ─────────────────────────────────────────────────────────────────

# Tasks plugin date emoji formats:
#   due date:   📅 YYYY-MM-DD
#   scheduled:  ⏳ YYYY-MM-DD
#   start:      🛫 YYYY-MM-DD
# Tasks with a future/past date are excluded.
# Tasks with no date marker at all are included as undated (shown below dated ones).

DATE_RE = re.compile(r'(?:[📅⏳🛫]\s*|\[\[)(\d{4}-\d{2}-\d{2})(?:\]\])?')
TASK_RE = re.compile(r'^\s*-\s*\[\s*\]\s*(.+)$', re.MULTILINE)
TAG_RE  = re.compile(r'(#\w+)')

def extractTasks():
    TODAY = date.today().strftime("%Y-%m-%d")  # recompute each call
    todayTasks   = []
    undatedTasks = []
    mdFiles = glob.glob(os.path.join(OBSIDIAN_VAULT, "**", "*.md"), recursive=True)

    for filepath in mdFiles:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        for match in TASK_RE.finditer(content):
            raw = match.group(1)
            dateMatches = DATE_RE.findall(raw)

            if dateMatches:
                # Has a date marker — include all dated tasks
                taskDate = min(dateMatches)
                bucket = todayTasks
            else:
                # No date marker — include as undated
                bucket = undatedTasks

            # Clean display text
            displayText = DATE_RE.sub('', raw).strip()
            tags = TAG_RE.findall(displayText)
            displayText = TAG_RE.sub('', displayText).strip()
            displayText = displayText.rstrip('|').strip()

            if not displayText:
                continue

            # Build relative path from vault root for Obsidian URI
            relPath = os.path.relpath(filepath, OBSIDIAN_VAULT)
            # Find line number for direct navigation in Obsidian
            lineNum = 0
            for i, line in enumerate(content.splitlines()):
                if raw.strip() in line and '- [ ]' in line:
                    lineNum = i + 1  # 1-indexed
                    break
            bucket.append({
                "text": displayText,
                "tags": ' '.join(tags) if tags else "",
                "file": os.path.basename(filepath),
                "path": filepath,
                "relPath": relPath,
                "line": lineNum,
                "raw":  raw.strip(),  # original line text for matching
                "dated": bool(dateMatches),
            })

    # Sort dated tasks: overdue first, then today, then future — all by date asc
    todayTasks.sort(key=lambda t: DATE_RE.findall(t["raw"])[0] if DATE_RE.findall(t["raw"]) else TODAY)

    # Tag overdue tasks so the frontend can highlight them
    for t in todayTasks:
        dates = DATE_RE.findall(t["raw"])
        if dates:
            t["overdue"] = min(dates) < TODAY
            t["dueDate"] = min(dates)
        else:
            t["overdue"] = False
            t["dueDate"] = None

    return todayTasks + undatedTasks

# ── SSE broadcast ─────────────────────────────────────────────────────────

# All active SSE clients subscribe to this queue-per-client list
_sseClients = []
_sseLock = threading.Lock()

def sseSubscribe():
    q = queue.Queue()
    with _sseLock:
        _sseClients.append(q)
    return q

def sseUnsubscribe(q):
    with _sseLock:
        try:
            _sseClients.remove(q)
        except ValueError:
            pass

def sseBroadcast(event, data):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
    with _sseLock:
        for q in list(_sseClients):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

# ── DroidCam ──────────────────────────────────────────────────────────────

DROIDCAM_IP   = "192.168.0.156"
DROIDCAM_PORT = 4747
DROIDCAM_SIZE = "3840x2160"
DROIDCAM_BASE = f"http://{DROIDCAM_IP}:{DROIDCAM_PORT}"

def droidcamPut(path):
    """Send a PUT request to the droidcam HTTP API on the phone."""
    import urllib.request
    url = DROIDCAM_BASE + path
    req = urllib.request.Request(url, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except Exception:
        return None

def getDroidcamInfo():
    import urllib.request
    try:
        with urllib.request.urlopen(DROIDCAM_BASE + "/v1/camera/info", timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None

def getDroidcamState():
    # Check if droidcam-cli process is running
    out, code = run(["pgrep", "-x", "droidcam-cli"])
    connected = code == 0
    info = getDroidcamInfo() if connected else None
    return {
        "connected": connected,
        "host":      f"{DROIDCAM_IP}:{DROIDCAM_PORT}",
        "zmValue":   info["zmValue"]   if info else 1.0,
        "zmMin":     info["zmMin"]     if info else 1.0,
        "zmMax":     info["zmMax"]     if info else 6.0,
        "focusMode": info["focusMode"] if info else 0,
    }

def isDroidcamReachable():
    """Check if the phone is reachable and droidcam is listening before connecting."""
    import socket
    try:
        sock = socket.create_connection((DROIDCAM_IP, DROIDCAM_PORT), timeout=2)
        sock.close()
        return True
    except (OSError, socket.timeout):
        return False
    except Exception:
        return False  # network unreachable

def toggleDroidcam():
    out, code = run(["pgrep", "-x", "droidcam-cli"])
    if code == 0:
        # Kill existing process
        run(["pkill", "-x", "droidcam-cli"])
    else:
        if not isDroidcamReachable():
            return {"error": "unreachable"}
        # Launch in background, detached from this process
        subprocess.Popen(
            ["droidcam-cli", "-size=" + DROIDCAM_SIZE, DROIDCAM_IP, str(DROIDCAM_PORT)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    return {"ok": True}

# ── pactl subscribe watcher ───────────────────────────────────────────────

def startSinkWatcher():
    """
    Monitors pactl subscribe output for sink change events.
    Fires an SSE broadcast whenever the default sink changes externally
    (e.g. StreamDeck, pavucontrol, any other tool).
    """
    def watch():
        proc = subprocess.Popen(
            ["pactl", "subscribe"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        lastSink = getDefaultSink()
        for line in proc.stdout:
            # We care about sink events: "Event 'change' on sink #N"
            if "'change'" in line and "sink #" in line.lower():
                current = getDefaultSink()
                if current != lastSink:
                    lastSink = current
                    sseBroadcast("sink-changed", getSinkState())
    t = threading.Thread(target=watch, daemon=True)
    t.start()

# ── Task completion ───────────────────────────────────────────────────────

def completeTask(filepath, rawText):
    """Mark a task as complete by replacing '- [ ]' with '- [x]' in the file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        # Match the exact task line and replace just the checkbox
        # Use the raw text to find the right line
        old = f"- [ ] {rawText}"
        new = f"- [x] {rawText}"
        if old not in content:
            return False
        content = content.replace(old, new, 1)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        return False

# ── playerctl watcher ─────────────────────────────────────────────────────

def startMediaWatcher():
    """
    Listens to D-Bus MPRIS PropertiesChanged signals directly.
    This is the correct approach — fired synchronously by the media player
    the instant any property changes, with zero polling latency.
    """
    def watch():
        import dbus
        import dbus.mainloop.glib
        from gi.repository import GLib

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()

        def onPropertiesChanged(interface, changed, invalidated, sender=None):
            # Only care about MPRIS Player interface changes
            if interface != "org.mpris.MediaPlayer2.Player":
                return
            relevant = {"Metadata", "PlaybackStatus", "Position", "Rate"}
            if not relevant.intersection(set(changed.keys()) | set(invalidated)):
                return

            # Get full state from playerctl
            state = getMediaState()

            # Override length directly from D-Bus signal payload if present
            # This bypasses the playerctl stale-cache issue entirely
            if "Metadata" in changed:
                meta = changed["Metadata"]
                if "mpris:length" in meta:
                    try:
                        state["length"] = int(meta["mpris:length"]) / 1e6
                    except Exception:
                        pass
                if "xesam:title" in meta:
                    try:
                        state["title"] = str(meta["xesam:title"])
                    except Exception:
                        pass
                if "xesam:artist" in meta:
                    try:
                        artists = meta["xesam:artist"]
                        state["artist"] = str(artists[0]) if hasattr(artists, '__iter__') and not isinstance(artists, str) else str(artists)
                    except Exception:
                        pass

            sseBroadcast("media-changed", state)

        # Match PropertiesChanged on any MPRIS player
        bus.add_signal_receiver(
            onPropertiesChanged,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path="/org/mpris/MediaPlayer2",
            sender_keyword="sender",
        )

        # Also watch for players appearing/disappearing
        def onNameOwnerChanged(name, old_owner, new_owner):
            if "mpris" in name.lower():
                state = getMediaState()
                sseBroadcast("media-changed", state)

        bus.add_signal_receiver(
            onNameOwnerChanged,
            dbus_interface="org.freedesktop.DBus",
            signal_name="NameOwnerChanged",
        )

        loop = GLib.MainLoop()
        loop.run()

    threading.Thread(target=watch, daemon=True).start()

# ── HTTP Handler ──────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default access log

    def handle_error(self, request, client_address):
        pass  # Suppress connection reset noise

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/status/toggles":
            vpn  = getVpnState()
            sink = getSinkState()
            jsonResp(self, {"vpn": vpn, "sink": sink})
        elif path == "/status/media":
            jsonResp(self, getMediaState())
        elif path == "/status/tasks":
            jsonResp(self, extractTasks())
        elif path == "/status/droidcam":
            jsonResp(self, getDroidcamState())
        elif path == "/colors.css":
            try:
                cssPath = os.path.expanduser("~/.cache/wal/colors.css")
                with open(cssPath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/css")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_response(404)
                self.end_headers()
        elif path == "/":
            try:
                with open(os.path.join(os.path.dirname(__file__), "index.html"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
        elif path == "/events":
            # Server-Sent Events stream
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            q = sseSubscribe()
            try:
                # Send initial ping so the client knows the connection is live
                self.wfile.write(b"event: ping\ndata: {}\n\n")
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=30)
                        self.wfile.write(msg)
                        self.wfile.flush()
                    except queue.Empty:
                        # Keepalive comment
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                sseUnsubscribe(q)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/toggle/vpn":
            toggleVpn()
            jsonResp(self, {"ok": True})
        elif path == "/toggle/sink":
            cycleSink()
            jsonResp(self, {"ok": True})
        elif path.startswith("/media/"):
            cmd = path.split("/media/")[-1]
            mediaCommand(cmd)
            jsonResp(self, {"ok": True})
        elif path == "/reload":
            sseBroadcast("reload", {})
            jsonResp(self, {"ok": True})
        elif path == "/exit":
            jsonResp(self, {"ok": True})
            # Kill the qutebrowser dashboard window after responding
            import threading
            def killDashboard():
                import time
                time.sleep(0.3)
                run(["xdotool", "search", "--classname", "dashboard", "windowkill"])
            threading.Thread(target=killDashboard, daemon=True).start()
        elif path == "/task/complete":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            success = completeTask(body.get("path", ""), body.get("raw", ""))
            jsonResp(self, {"ok": success})
        elif path == "/toggle/droidcam":
            result = toggleDroidcam()
            jsonResp(self, result if result else {"ok": True})
        elif path == "/droidcam/zoom":
            # Expects JSON body: {"value": 2.5}
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            value = float(body.get("value", 1.0))
            value = round(max(1.0, min(6.0, value)), 2)
            droidcamPut(f"/v3/camera/zoom/{value}")
            jsonResp(self, {"ok": True})
        elif path == "/droidcam/autofocus":
            droidcamPut("/v1/camera/autofocus")
            jsonResp(self, {"ok": True})
        elif path.startswith("/droidcam/focusmode/"):
            mode = path.split("/")[-1]
            droidcamPut(f"/v1/camera/autofocus_mode/{mode}")
            jsonResp(self, {"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    startSinkWatcher()
    startMediaWatcher()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard server running on port {PORT}")
    server.serve_forever()
