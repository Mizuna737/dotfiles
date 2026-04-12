#!/usr/bin/env python3
"""
dashboardServer.py
Custom HTTP bridge for the AwesomeWM dashboard.
Written with Claude (Anthropic) - March 2026.

Handles system toggles, media control, Obsidian task management,
DroidCam integration, and Todoist shopping list sync.

Todoist integration uses the Todoist API v1:
  https://developer.todoist.com/api/v1/
"""

import json
import subprocess
import re
import os
import glob
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import urlparse
import urllib.request
import urllib.error
import threading
import queue
import gi
import configparser

gi.require_version("GLib", "2.0")

OBSIDIAN_VAULT = os.path.expanduser("~/Documents/The Vault")


def loadTodoistConfig():
    config = configparser.ConfigParser()
    configPath = os.path.expanduser("~/.config/dashboard/todoist.conf")
    # configparser requires a section header
    with open(configPath) as f:
        config.read_string("[todoist]\n" + f.read())
    return config["todoist"]


todoistConf = loadTodoistConfig()
TODOIST_API_TOKEN = todoistConf.get("TODOIST_API_TOKEN", "")
TODOIST_CLIENT_ID = todoistConf.get("TODOIST_CLIENT_ID", "")
TODOIST_CLIENT_SECRET = todoistConf.get("TODOIST_CLIENT_SECRET", "")
TODOIST_PROJECT_NAME = "Shopping List"
SHOPPING_LIST_FILE = os.path.join(OBSIDIAN_VAULT, "Notes/Shopping List.md")
NICOLE_PROJECT_NAME = "Household priorities"
NICOLE_PRIORITIES_FILE = os.path.join(OBSIDIAN_VAULT, "Notes/Nicole's Priorities.md")

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


def getEndOfWeek():
    today = date.today()
    # Days until Sunday (weekday: Mon=0, Sun=6)
    daysUntilSunday = 6 - today.weekday()
    return today + timedelta(days=daysUntilSunday)


PRIORITY_ORDER = {"⏫": 0, "🔼": 1, "": 2, "🔽": 3, "⏬": 4}
PRIORITY_RE = re.compile(r"[⏫🔼🔽⏬]")
PONDER_RE = re.compile(r"#ponder")
TODOIST_ID_RE = re.compile(r"\s*\[todoist::\s*[\w]+\]")
DESC_RE = re.compile(r"\s*\[desc::\s*(.+?)\]")


def getPriority(text):
    for p in ["⏫", "🔼", "🔽", "⏬"]:
        if p in text:
            return p
    return ""


def isImportant(text):
    p = getPriority(text)
    return p in ("⏫", "🔼")


def buildMatrix():
    today = date.today()
    endOfWeek = getEndOfWeek()
    todayStr = today.strftime("%Y-%m-%d")
    endOfWeekStr = endOfWeek.strftime("%Y-%m-%d")

    allTasks = extractTasks()

    q1, q2, q3, ponder = [], [], [], []

    for t in allTasks:
        raw = t["raw"]
        dueDate = t.get("dueDate")
        important = isImportant(raw)
        isPonder = "#ponder" in raw

        if isPonder:
            ponder.append(t)
            continue

        if dueDate:
            urgent = dueDate <= endOfWeekStr
            if urgent:
                q1.append(t)
            else:
                q3.append(t)
        else:
            q2.append(t)

    # Nicole's priorities float to the top of this week's quadrant
    q1.sort(key=lambda t: (
        0 if "#nicole" in t.get("tags", "") else 1,
        t.get("dueDate") or "9999",
        PRIORITY_ORDER.get(getPriority(t["raw"]), 2),
    ))
    return {"q1": q1, "q2": q2, "q3": q3, "ponder": ponder}


# --- Shopping List ──────────────────────────────────────────────────────────────────


def todoistPollLoop():
    while True:
        try:
            syncShoppingListFromTodoist()
        except Exception as e:
            print(f"Todoist poll error: {e}")
        try:
            syncNicolePrioritiesFromTodoist()
        except Exception as e:
            print(f"Nicole priorities poll error: {e}")
        time.sleep(60)


def todoistRequest(method, path, body=None):
    url = f"https://api.todoist.com/api/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TODOIST_API_TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status == 204:
                return {}
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": str(e)}


def getTodoistProjectId(projectName=None):
    if projectName is None:
        projectName = TODOIST_PROJECT_NAME
    resp = todoistRequest("GET", "/projects")
    projects = resp.get("results", resp) if isinstance(resp, dict) else resp
    for p in projects:
        if p["name"] == projectName:
            return p["id"]
    return None


def getTodoistTasks(projectId):
    resp = todoistRequest("GET", f"/tasks?project_id={projectId}")
    return resp.get("results", resp) if isinstance(resp, dict) else resp


def createTodoistTask(content, projectId):
    return todoistRequest(
        "POST", "/tasks", {"content": content, "project_id": projectId}
    )


def closeTodoistTask(taskId):
    return todoistRequest("POST", f"/tasks/{taskId}/close")


def deleteTodoistTask(taskId):
    return todoistRequest("DELETE", f"/tasks/{taskId}")


def readShoppingList():
    try:
        with open(SHOPPING_LIST_FILE, "r", encoding="utf-8") as f:
            return f.readlines()
    except Exception:
        return []


def writeShoppingList(lines):
    with open(SHOPPING_LIST_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


def getShoppingListItems():
    lines = readShoppingList()
    items = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*-\s*\[( |x)\]\s*(.+)$", line)
        if m:
            completed = m.group(1) == "x"
            text = m.group(2).strip()
            todoistId = None
            idMatch = re.search(r"\[todoist::\s*([\w]+)\]", text)
            if idMatch:
                todoistId = idMatch.group(1)
                text = re.sub(r"\s*\[todoist::\s*\w+\]", "", text).strip()
            items.append(
                {
                    "line": i,
                    "text": text,
                    "todoistId": todoistId,
                    "completed": completed,
                    "raw": line.rstrip(),
                }
            )
    return items


def addShoppingItem(text, todoistId):
    lines = readShoppingList()
    idxStr = next((i for i, l in enumerate(lines) if l.strip() == "## Items"), None)
    newLine = f"- [ ] {text} [todoist:: {todoistId}]\n"
    if idxStr is not None:
        insertAt = idxStr + 1
        while insertAt < len(lines) and (
            lines[insertAt].strip() == "" or lines[insertAt].strip().startswith("<!--")
        ):
            insertAt += 1
        lines.insert(insertAt, newLine)
    else:
        lines.append(newLine)
    writeShoppingList(lines)


def completeShoppingItem(todoistId):
    lines = readShoppingList()
    for i, line in enumerate(lines):
        if f"[todoist:: {todoistId}]" in line and "- [ ]" in line:
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            break
    writeShoppingList(lines)


def removeShoppingItem(todoistId):
    lines = readShoppingList()
    lines = [l for l in lines if f"[todoist:: {todoistId}]" not in l]
    writeShoppingList(lines)


def syncShoppingListFromTodoist():
    """Full sync — rebuild vault file from Todoist state."""
    projectId = getTodoistProjectId()
    if not projectId:
        return
    tasks = getTodoistTasks(projectId)
    if isinstance(tasks, dict) and "error" in tasks:
        return
    lines = readShoppingList()
    # Keep everything up to and including ## Items header
    headerEnd = next((i for i, l in enumerate(lines) if l.strip() == "## Items"), None)
    if headerEnd is not None:
        newLines = lines[: headerEnd + 1] + ["\n"]
    else:
        newLines = lines + ["## Items\n", "\n"]
    for task in tasks:
        newLines.append(f"- [ ] {task['content']} [todoist:: {task['id']}]\n")
    writeShoppingList(newLines)


# ── Nicole's Priorities ──────────────────────────────────────────────────────


def syncNicolePrioritiesFromTodoist():
    """Full sync — rebuild Nicole's priorities note from Todoist state."""
    projectId = getTodoistProjectId(NICOLE_PROJECT_NAME)
    if not projectId:
        return
    tasks = getTodoistTasks(projectId)
    if isinstance(tasks, dict) and "error" in tasks:
        return
    try:
        with open(NICOLE_PRIORITIES_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        lines = []
    headerEnd = next((i for i, l in enumerate(lines) if l.strip() == "## Tasks"), None)
    if headerEnd is not None:
        newLines = lines[: headerEnd + 1] + ["\n"]
    else:
        newLines = [
            "# Nicole's Priorities\n",
            "\n",
            'Synced from Todoist "This week\'s priorities". Do not edit manually.\n',
            "\n",
            "## Tasks\n",
            "\n",
        ]
    for task in tasks:
        due = task.get("due") or {}
        dueDate = due.get("date", "")
        dateStr = f" [[{dueDate}]]" if dueDate else ""
        desc = (task.get("description") or "").strip()
        descStr = f" [desc:: {desc}]" if desc else ""
        newLines.append(f"- [ ] {task['content']} #nicole{dateStr}{descStr} [todoist:: {task['id']}]\n")
    with open(NICOLE_PRIORITIES_FILE, "w", encoding="utf-8") as f:
        f.writelines(newLines)


def updateTodoistTaskDue(taskId, newRaw):
    """Push due date from newRaw [[YYYY-MM-DD]] to Todoist. Clears due if no date found."""
    dateMatch = re.search(r"\[\[(\d{4}-\d{2}-\d{2})\]\]", newRaw)
    body = {"due_date": dateMatch.group(1)} if dateMatch else {"due_date": None}
    result = todoistRequest("POST", f"/tasks/{taskId}", body)
    print(f"updateTodoistTaskDue {taskId} body={body} result={result}")


def syncCompletedNicoleTasks():
    """Close any completed Nicole priority tasks in Todoist."""
    try:
        with open(NICOLE_PRIORITIES_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return
    for line in lines:
        m = re.match(r"^\s*-\s*\[x\]\s*(.+)$", line)
        if m:
            idMatch = re.search(r"\[todoist::\s*([\w]+)\]", m.group(1))
            if idMatch:
                closeTodoistTask(idMatch.group(1))


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
    import time

    time.sleep(1)
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

    metaOut, _ = run(
        [
            "playerctl",
            "metadata",
            "--format",
            "{{xesam:title}}|{{xesam:artist}}|{{xesam:album}}",
        ]
    )
    lines = metaOut.split("|")
    title = lines[0] if len(lines) > 0 else ""
    artist = lines[1] if len(lines) > 1 else ""
    album = lines[2] if len(lines) > 2 else ""

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
        "title": title,
        "artist": artist,
        "album": album,
        "position": posF,
        "length": lenF,
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

DATE_RE = re.compile(r"(?:[📅⏳🛫]\s*|\[\[)(\d{4}-\d{2}-\d{2})(?:\]\])?")
TASK_RE = re.compile(r"^\s*-\s*\[([\ /])\]\s*(.+)$", re.MULTILINE)
TAG_RE = re.compile(r"(#\w+)")
DOMAIN_TAGS = {"#work", "#household", "#personal"}


def extractTasks():
    TODAY = date.today().strftime("%Y-%m-%d")  # recompute each call
    todayTasks = []
    undatedTasks = []
    mdFiles = glob.glob(os.path.join(OBSIDIAN_VAULT, "**", "*.md"), recursive=True)

    for filepath in mdFiles:
        # Skip shopping list — handled separately via Todoist
        if os.path.basename(filepath) == "Shopping List.md":
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        for match in TASK_RE.finditer(content):
            marker = match.group(1)  # ' ' or '/'
            raw = match.group(2)
            dateMatches = DATE_RE.findall(raw)

            if dateMatches:
                # Has a date marker — include all dated tasks
                taskDate = min(dateMatches)
                bucket = todayTasks
            else:
                # No date marker — include as undated
                bucket = undatedTasks

            # Clean display text
            displayText = DATE_RE.sub("", raw).strip()
            tags = TAG_RE.findall(displayText)
            domain = next((t for t in tags if t in DOMAIN_TAGS), "")
            displayText = TAG_RE.sub("", displayText).strip()
            displayText = TODOIST_ID_RE.sub("", displayText).strip()
            descMatch = DESC_RE.search(displayText)
            description = descMatch.group(1).strip() if descMatch else ""
            displayText = DESC_RE.sub("", displayText).strip()
            displayText = displayText.rstrip("|").strip()

            if not displayText:
                continue

            # Build relative path from vault root for Obsidian URI
            relPath = os.path.relpath(filepath, OBSIDIAN_VAULT)
            # Find line number for direct navigation in Obsidian
            lineNum = 0
            checkboxStr = f"- [{'/' if marker == '/' else ' '}]"
            for i, line in enumerate(content.splitlines()):
                if raw.strip() in line and checkboxStr in line:
                    lineNum = i + 1  # 1-indexed
                    break
            bucket.append(
                {
                    "text": displayText,
                    "tags": " ".join(tags) if tags else "",
                    "domain": domain,
                    "description": description,
                    "file": os.path.basename(filepath),
                    "path": filepath,
                    "relPath": relPath,
                    "line": lineNum,
                    "raw": raw.strip(),  # original line text for matching
                    "dated": bool(dateMatches),
                    "status": "inProgress" if marker == "/" else "todo",
                }
            )

    # Sort dated tasks: overdue first, then today, then future — all by date asc
    todayTasks.sort(
        key=lambda t: (
            DATE_RE.findall(t["raw"])[0] if DATE_RE.findall(t["raw"]) else TODAY,
            PRIORITY_ORDER.get(getPriority(t["raw"]), 2),
        )
    )

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


_eisenhowerClients = []
_eisenhowerLock = threading.Lock()


def eisenhowerSubscribe():
    q = queue.Queue()
    with _eisenhowerLock:
        _eisenhowerClients.append(q)
    return q


def eisenhowerUnsubscribe(q):
    with _eisenhowerLock:
        try:
            _eisenhowerClients.remove(q)
        except ValueError:
            pass


def eisenhowerBroadcast(data):
    msg = f"event: matrix-update\ndata: {json.dumps(data)}\n\n".encode()
    with _eisenhowerLock:
        for q in list(_eisenhowerClients):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass


def syncCompletedShoppingItems():
    """Close any completed shopping items in Todoist that haven't been closed yet."""
    lines = readShoppingList()
    for line in lines:
        m = re.match(r"^\s*-\s*\[x\]\s*(.+)$", line)
        if m:
            text = m.group(1)
            idMatch = re.search(r"\[todoist::\s*([\w]+)\]", text)
            if idMatch:
                todoistId = idMatch.group(1)
                closeTodoistTask(todoistId)


def startVaultWatcher():
    def watch():
        proc = subprocess.Popen(
            [
                "inotifywait",
                "-m",
                "-r",
                "-e",
                "close_write",
                "--include",
                r".*\.md$",
                OBSIDIAN_VAULT,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for line in proc.stdout:
            eisenhowerBroadcast(buildMatrix())
            if "Shopping List.md" in line:
                syncCompletedShoppingItems()
            if "Nicole's Priorities.md" in line:
                syncCompletedNicoleTasks()

    t = threading.Thread(target=watch, daemon=True)
    t.start()


# ── DroidCam ──────────────────────────────────────────────────────────────

DROIDCAM_IP = "192.168.0.156"
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
        "host": f"{DROIDCAM_IP}:{DROIDCAM_PORT}",
        "zmValue": info["zmValue"] if info else 1.0,
        "zmMin": info["zmMin"] if info else 1.0,
        "zmMax": info["zmMax"] if info else 6.0,
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
            start_new_session=True,
        )
    return {"ok": True}


# ── bgremove ─────────────────────────────────────────────────────────────────

import signal as _signal

BG_CACHE_FILE = os.path.expanduser("~/.cache/bgremove.bg")
_BG_VALID_MODES = {"off", "blur", "green", "black"}
WALLPAPER_DIR = os.path.expanduser("~/wallpapers")


def getBgremoveState():
    out, code = run(["pgrep", "-f", "bgremove.py"])
    bgRunning = code == 0

    if os.path.exists(BG_CACHE_FILE):
        with open(BG_CACHE_FILE) as f:
            mode = f.read().strip() or "blur"
    else:
        mode = "blur"

    return {"running": bgRunning, "mode": mode}


def _signalBgremove():
    out, code = run(["pgrep", "-f", "bgremove.py"])
    if code != 0:
        run(["systemctl", "--user", "start", "bgremove"])
    else:
        for pid in out.strip().split():
            try:
                os.kill(int(pid), _signal.SIGUSR1)
            except Exception:
                pass


def setBgremoveMode(mode):
    if mode not in _BG_VALID_MODES:
        return {"error": f"Invalid mode: {mode}"}

    with open(BG_CACHE_FILE, "w") as f:
        f.write(mode)

    _signalBgremove()
    return {"ok": True, "mode": mode}



_bgPickerLock = threading.Lock()


def pickBgremoveImage():
    if not _bgPickerLock.acquire(blocking=False):
        return {"error": "Image picker already open"}
    try:
        return _pickBgremoveImageInner()
    finally:
        _bgPickerLock.release()


def _pickBgremoveImageInner():
    exts = ("*.jpg", "*.jpeg", "*.png", "*.webp")
    images = sorted(
        p for pat in exts
        for p in glob.glob(os.path.join(WALLPAPER_DIR, pat))
    )
    if not images:
        return {"error": "No images found in wallpapers directory"}

    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}

    proc = subprocess.Popen(
        ["nsxiv", "-ot"] + images,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, env=env
    )

    stdout, _ = proc.communicate()
    selected = stdout.strip()
    if not selected:
        return {"cancelled": True}

    imagePath = selected.splitlines()[0]
    with open(BG_CACHE_FILE, "w") as f:
        f.write(imagePath)

    _signalBgremove()
    return {"ok": True, "mode": imagePath}


# ── System stats ─────────────────────────────────────────────────────────────

_lastCpuStat = None


def getCpuPercent():
    global _lastCpuStat
    with open("/proc/stat") as f:
        fields = list(map(int, f.readline().split()[1:]))
    idle, total = fields[3], sum(fields)
    if _lastCpuStat is None:
        _lastCpuStat = (idle, total)
        return 0.0
    prevIdle, prevTotal = _lastCpuStat
    _lastCpuStat = (idle, total)
    diffTotal = total - prevTotal
    return round(100.0 * (1.0 - (idle - prevIdle) / diffTotal), 1) if diffTotal else 0.0


def getSysStats():
    cpu = getCpuPercent()

    memInfo = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, val = line.split(":", 1)
            memInfo[key.strip()] = int(val.split()[0])  # kB
    ramTotal = memInfo.get("MemTotal", 1)
    ramUsed  = ramTotal - memInfo.get("MemAvailable", 0)

    gpuUtil = vramUsed = vramTotal = 0
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split(",")
            gpuUtil   = int(parts[0].strip())
            vramUsed  = int(parts[1].strip())
            vramTotal = int(parts[2].strip())
    except Exception:
        pass

    return {
        "cpu":  cpu,
        "ram":  {"used": ramUsed,  "total": ramTotal},   # kB
        "gpu":  gpuUtil,
        "vram": {"used": vramUsed, "total": vramTotal},  # MiB
    }


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
            text=True,
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


def setTaskStatus(filepath, rawText, marker):
    """Set task checkbox to the given marker: 'x', '/', or '-'."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        new = f"- [{marker}] {rawText}"
        for src in ("- [ ] ", "- [/] "):
            old = f"{src}{rawText}"
            if old in content:
                content = content.replace(old, new, 1)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                return True
        return False
    except Exception:
        return False


def completeTask(filepath, rawText):
    return setTaskStatus(filepath, rawText, "x")


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
                        state["artist"] = (
                            str(artists[0])
                            if hasattr(artists, "__iter__")
                            and not isinstance(artists, str)
                            else str(artists)
                        )
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
            vpn = getVpnState()
            sink = getSinkState()
            jsonResp(self, {"vpn": vpn, "sink": sink})
        elif path == "/status/media":
            jsonResp(self, getMediaState())
        elif path == "/status/tasks":
            jsonResp(self, extractTasks())
        elif path == "/status/droidcam":
            jsonResp(self, getDroidcamState())
        elif path == "/status/bgremove":
            jsonResp(self, getBgremoveState())
        elif path == "/status/sysstat":
            jsonResp(self, getSysStats())
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
                with open(
                    os.path.join(os.path.dirname(__file__), "index.html"), "rb"
                ) as f:
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
        elif path == "/eisenhower":
            try:
                htmlPath = os.path.join(os.path.dirname(__file__), "eisenhower.html")
                with open(htmlPath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()

        elif path.endswith(".js"):
            jsPath = os.path.join(os.path.dirname(__file__), os.path.basename(path))
            try:
                with open(jsPath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()

        elif path == "/eisenhower/data":
            jsonResp(self, buildMatrix())

        elif path == "/eisenhower/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            q = eisenhowerSubscribe()
            try:
                self.wfile.write(b"event: ping\ndata: {}\n\n")
                self.wfile.flush()
                # Send initial data immediately
                initial = f"event: matrix-update\ndata: {json.dumps(buildMatrix())}\n\n".encode()
                self.wfile.write(initial)
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=30)
                        self.wfile.write(msg)
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                eisenhowerUnsubscribe(q)
        elif path == "/shopping/items":
            jsonResp(self, getShoppingListItems())
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
        elif path == "/eisenhower/exit":
            jsonResp(self, {"ok": True})

            def killWindow():
                import time

                time.sleep(0.3)
                run(["xdotool", "search", "--classname", "eisenhower", "windowkill"])

            threading.Thread(target=killWindow, daemon=True).start()
        elif path == "/todoist/webhook":
            length = int(self.headers.get("Content-Length", 0))
            rawBody = self.rfile.read(length)
            body = json.loads(rawBody) if length else {}
            event = body.get("event_name", "")
            data = body.get("event_data", {})
            taskId = str(data.get("id", ""))
            projectId = str(data.get("project_id", ""))

            # Verify it's from our Shopping List project
            ourProjectId = getTodoistProjectId()
            if projectId != str(ourProjectId):
                jsonResp(self, {"ok": True, "skipped": True})
                return

            if event == "item:added":
                addShoppingItem(data.get("content", ""), taskId)
            elif event in ("item:completed", "item:updated") and data.get("checked"):
                completeShoppingItem(taskId)
            elif event == "item:deleted":
                removeShoppingItem(taskId)

            jsonResp(self, {"ok": True})

        elif path == "/shopping/add":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            text = body.get("text", "").strip()
            if not text:
                jsonResp(self, {"ok": False, "error": "No text"}, 400)
                return
            projectId = getTodoistProjectId()
            if not projectId:
                jsonResp(self, {"ok": False, "error": "Project not found"}, 500)
                return
            task = createTodoistTask(text, projectId)
            if "error" in task:
                jsonResp(self, {"ok": False, "error": task["error"]}, 500)
                return
            addShoppingItem(text, task["id"])
            jsonResp(self, {"ok": True, "id": task["id"]})

        elif path == "/shopping/complete":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            todoistId = body.get("todoistId", "")
            if todoistId:
                closeTodoistTask(todoistId)
                completeShoppingItem(todoistId)
            jsonResp(self, {"ok": True})

        elif path == "/shopping/sync":
            syncShoppingListFromTodoist()
            jsonResp(self, {"ok": True})
        elif path == "/nicole/add":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            text = body.get("text", "").strip()
            if not text:
                jsonResp(self, {"ok": False, "error": "No text"}, 400)
                return
            projectId = getTodoistProjectId(NICOLE_PROJECT_NAME)
            if not projectId:
                jsonResp(self, {"ok": False, "error": "Project not found"}, 500)
                return
            taskBody = {"content": text, "project_id": projectId}
            due = body.get("due", "").strip()
            if due:
                if re.match(r"^\d{4}-\d{2}-\d{2}$", due):
                    taskBody["due_date"] = due
                else:
                    taskBody["due_string"] = due
            task = todoistRequest("POST", "/tasks", taskBody)
            if "error" in task:
                jsonResp(self, {"ok": False, "error": task["error"]}, 500)
                return
            syncNicolePrioritiesFromTodoist()
            jsonResp(self, {"ok": True, "id": task["id"]})
        elif path == "/task/modify":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            filepath = body.get("path", "")
            oldRaw = body.get("oldRaw", "")
            newRaw = body.get("newRaw", "")
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                prefix = None
                for p in ("- [ ] ", "- [/] "):
                    if f"{p}{oldRaw}" in content:
                        prefix = p
                        break
                if not prefix:
                    jsonResp(self, {"ok": False, "error": "Task not found"}, 404)
                    return
                content = content.replace(f"{prefix}{oldRaw}", f"{prefix}{newRaw}", 1)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                # Sync due date back to Todoist for Nicole tasks
                idMatch = re.search(r"\[todoist::\s*([\w]+)\]", newRaw)
                if idMatch:
                    updateTodoistTaskDue(idMatch.group(1), newRaw)
                jsonResp(self, {"ok": True})
            except Exception as e:
                jsonResp(self, {"ok": False, "error": str(e)}, 500)
        elif path == "/task/complete":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            success = completeTask(body.get("path", ""), body.get("raw", ""))
            jsonResp(self, {"ok": success})
        elif path == "/task/setstatus":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            markerMap = {"complete": "x", "inProgress": "/", "cancelled": "-"}
            marker = markerMap.get(body.get("status", ""))
            if not marker:
                jsonResp(self, {"ok": False, "error": "Invalid status"}, 400)
                return
            success = setTaskStatus(body.get("path", ""), body.get("raw", ""), marker)
            jsonResp(self, {"ok": success})
        elif path == "/obsidian/open":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            uri = body.get("uri", "")
            if uri.startswith("obsidian://"):
                env = os.environ.copy()
                env["DISPLAY"] = ":0"
                env["XAUTHORITY"] = "/home/max/.Xauthority"
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["HOME"] = "/home/max"
                subprocess.Popen(["xdg-open", uri], env=env)
                jsonResp(self, {"ok": True})
            else:
                jsonResp(self, {"ok": False, "error": "Invalid URI"}, 400)
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
        elif path == "/bgremove/mode":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            mode = body.get("mode", "")
            jsonResp(self, setBgremoveMode(mode))
        elif path == "/bgremove/pickimage":
            jsonResp(self, pickBgremoveImage())
        elif path == "/webhook":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            action = body.get("action")
            if action == "captureTask":
                task = body.get("task", "").strip()
                due = body.get("due", "skip").strip() or "skip"
                priority = body.get("priority", "skip").strip() or "skip"
                if not task:
                    jsonResp(self, {"ok": False, "error": "No task text"}, 400)
                    return
                env = os.environ.copy()
                env["DISPLAY"] = ":0"
                env["XAUTHORITY"] = "/home/max/.Xauthority"
                env["XDG_RUNTIME_DIR"] = "/run/user/1000"
                env["HOME"] = "/home/max"
                try:
                    result = subprocess.run(
                        ["/home/max/Scripts/captureTask.sh", task, due, priority],
                        capture_output=True,
                        text=True,
                        env=env,
                        timeout=15,
                    )
                    if result.returncode == 0:
                        jsonResp(self, {"ok": True, "action": action, "task": task})
                    else:
                        jsonResp(self, {"ok": False, "error": result.stderr}, 500)
                except subprocess.TimeoutExpired:
                    jsonResp(self, {"ok": False, "error": "Timeout"}, 500)
            else:
                jsonResp(self, {"ok": False, "error": f"Unknown action: {action}"}, 400)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    startSinkWatcher()
    startMediaWatcher()
    startVaultWatcher()

    try:
        syncShoppingListFromTodoist()
        print("Todoist initial sync complete")
    except Exception as e:
        print(f"Todoist initial sync error: {e}")
    try:
        syncNicolePrioritiesFromTodoist()
        print("Nicole priorities initial sync complete")
    except Exception as e:
        print(f"Nicole priorities initial sync error: {e}")

    todoistThread = threading.Thread(target=todoistPollLoop, daemon=True)
    todoistThread.start()

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard server running on port {PORT}")
    server.serve_forever()
