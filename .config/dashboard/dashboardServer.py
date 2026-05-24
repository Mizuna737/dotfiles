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
import sys
import socket
import glob
import time
import sqlite3
import uuid
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import urlparse
import urllib.request
import urllib.error
import threading
import queue
import gi
import configparser
import pynvml
import requests

sys.path.insert(0, os.path.dirname(__file__))
from taskCreate import createTask, resolveDueDate
from diskHealthRefresh import refreshDiskHealth
from chatServer import initChatDb, ChatRequestHandler

gi.require_version("GLib", "2.0")

# ── Monkey-patch to keep SSE connections alive after handler returns ─────
_orig_finish = BaseHTTPRequestHandler.finish
def _patched_finish(self):
    if getattr(self, 'is_sse_stream', False):
        self.wfile.flush()
    else:
        _orig_finish(self)
BaseHTTPRequestHandler.finish = _patched_finish

OBSIDIAN_VAULT = os.path.expanduser("~/Vault")


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
    q1.sort(
        key=lambda t: (
            0 if "#nicole" in t.get("tags", "") else 1,
            t.get("dueDate") or "9999",
            PRIORITY_ORDER.get(getPriority(t["raw"]), 2),
        )
    )
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


def getWallTodoistTasks(filterStr, projectName, limit):
    """Fetch tasks for the wall list widget using existing token/helper."""
    path = "/tasks?"
    params = []
    if projectName:
        pid = getTodoistProjectId(projectName)
        if pid:
            params.append(f"project_id={pid}")
    if filterStr:
        import urllib.parse as _up
        params.append("filter=" + _up.quote(filterStr))
    if params:
        path += "&".join(params)
    resp = todoistRequest("GET", path)
    tasks = resp.get("results", resp) if isinstance(resp, dict) else resp
    if not isinstance(tasks, list):
        return []
    out = []
    for t in tasks[:limit]:
        due = None
        if t.get("due"):
            due = t["due"].get("date") or t["due"].get("datetime")
        out.append({
            "content": t.get("content", ""),
            "due": due,
            "priority": t.get("priority", 1),
            "isCompleted": t.get("is_completed", False),
            "id": t.get("id", ""),
        })
    return out


def getWallObsidianTasks(relPath, filterMode, limit):
    """Read tasks from an Obsidian markdown file."""
    import re as _re
    fullPath = os.path.join(OBSIDIAN_VAULT, relPath)
    try:
        with open(fullPath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []
    tasks = []
    for line in lines:
        m = _re.match(r'\s*-\s+\[([ xX])\]\s+(.*)', line)
        if not m:
            continue
        completed = m.group(1).lower() == 'x'
        text = m.group(2).strip()
        # Extract due date from Obsidian Tasks plugin format: 📅 YYYY-MM-DD
        due = None
        dueMatch = _re.search(r'📅\s*(\d{4}-\d{2}-\d{2})', text)
        if dueMatch:
            due = dueMatch.group(1)
            text = text[:dueMatch.start()].strip()
        if filterMode == 'incomplete' and completed:
            continue
        if filterMode == 'complete' and not completed:
            continue
        tasks.append({"content": text, "due": due, "completed": completed})
        if len(tasks) >= limit:
            break
    return tasks


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
        newLines.append(
            f"- [ ] {task['content']} #nicole{dateStr}{descStr} [todoist:: {task['id']}]\n"
        )
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


def getQwenState():
    out, _ = run(["systemctl", "--user", "is-active", "llamaServer.service"])
    active = out.strip() == "active"
    return {"active": active, "label": "Running" if active else "Stopped"}


def toggleQwen():
    state = getQwenState()
    cmd = "stop" if state["active"] else "start"
    run(["systemctl", "--user", cmd, "llamaServer.service"])
    import time
    time.sleep(1)
    sseBroadcast("qwen-changed", getQwenState())


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


def getSinkState():
    current = getDefaultSink()
    label = SINK_NAMES.get(current, current.split(".")[-1])
    return {"active": True, "label": label, "sink": current}


# ── Media (playerctl) ─────────────────────────────────────────────────────


def _activePlayer():
    players, code = run(["playerctl", "-l"])
    if code != 0 or not players.strip():
        return None
    names = [p.strip() for p in players.strip().splitlines() if p.strip()]
    firstPaused = None
    for p in names:
        status, _ = run(["playerctl", "-p", p, "status"])
        status = status.strip()
        if status == "Playing":
            return p
        if status == "Paused" and firstPaused is None:
            firstPaused = p
    return firstPaused


def getMediaState():
    player = _activePlayer()
    if player is None:
        return {}

    status, code = run(["playerctl", "-p", player, "status"])
    if code != 0 or status.strip() in ("No players found", ""):
        return {}
    status = status.strip()

    metaOut, _ = run(
        [
            "playerctl",
            "-p",
            player,
            "metadata",
            "--format",
            "{{xesam:title}}|{{xesam:artist}}|{{xesam:album}}",
        ]
    )
    lines = metaOut.split("|")
    title = lines[0] if len(lines) > 0 else ""
    artist = lines[1] if len(lines) > 1 else ""
    album = lines[2] if len(lines) > 2 else ""

    rawPos, _ = run(["playerctl", "-p", player, "position"])
    try:
        posF = float(rawPos)
    except Exception:
        posF = 0

    rawLen, _ = run(["playerctl", "-p", player, "metadata", "mpris:length"])
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
        player = _activePlayer()
        if player:
            run(["playerctl", "-p", player, cmd])


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
            if not domain and "#nicole" in tags:
                domain = "#household"
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

_wallClients = []
_wallLock = threading.Lock()
_icsCache = {}
_wallUploadsDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wall-uploads")
_wallLayoutPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wall-layout.json")


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


def wallSubscribe():
    q = queue.Queue(maxsize=10)
    with _wallLock:
        _wallClients.append(q)
    return q


def wallUnsubscribe(q):
    with _wallLock:
        try:
            _wallClients.remove(q)
        except ValueError:
            pass


def wallBroadcast(eventName, data):
    msg = f"event: {eventName}\ndata: {json.dumps(data)}\n\n"
    with _wallLock:
        for q in list(_wallClients):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass


def getWallLayout():
    if not os.path.exists(_wallLayoutPath):
        return {}
    try:
        with open(_wallLayoutPath, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def saveWallLayout(data):
    os.makedirs(os.path.dirname(_wallLayoutPath), exist_ok=True)
    with open(_wallLayoutPath, "w") as f:
        json.dump(data, f, indent=2)
    wallBroadcast("layoutUpdated", {})


def fetchIcs(url):
    import time
    now = time.time()
    cached = _icsCache.get(url)
    if cached and now - cached["ts"] < 900:
        return cached["events"]
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            rawBytes = resp.read()
        raw = rawBytes.decode("utf-8", errors="replace")
    except Exception as e:
        return []
    events = parseIcs(raw)
    _icsCache[url] = {"ts": now, "events": events}
    return events


def parseIcs(raw):
    import re as _re
    from datetime import datetime, timezone, timedelta, date as _date

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None

    raw = _re.sub(r'\r\n[ \t]', '', raw)
    raw = _re.sub(r'\n[ \t]', '', raw)

    today = datetime.now(timezone.utc)
    windowStart = today - timedelta(days=60)
    windowEnd   = today + timedelta(days=180)

    def parseDtLine(block, name):
        """Return (isoStr, allDay, tzid) for a DTSTART or DTEND line."""
        m = _re.search(rf'^{name}(;[^:]+)?:(.+)$', block, _re.MULTILINE)
        if not m:
            return None, False, None
        params = m.group(1) or ''
        val = m.group(2).strip()
        tzidMatch = _re.search(r'TZID=([^;:]+)', params)
        tzid = tzidMatch.group(1) if tzidMatch else None

        if _re.match(r'^\d{8}$', val):
            # All-day: return bare date string so client parses as local date, not UTC midnight
            return val[:4] + '-' + val[4:6] + '-' + val[6:8], True, None

        val = val.rstrip('Z')
        try:
            dt = datetime.strptime(val[:15], '%Y%m%dT%H%M%S')
        except Exception:
            return None, False, None

        if tzid and ZoneInfo:
            try:
                tz = ZoneInfo(tzid)
                dt = dt.replace(tzinfo=tz).astimezone(timezone.utc)
            except Exception:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.isoformat(), False, tzid

    def expandRrule(rrule, dtstart_iso, allDay, summary, dtend_iso):
        """Expand an RRULE string into event dicts within the window."""
        instances = []
        try:
            start = datetime.fromisoformat(dtstart_iso)
            if not start.tzinfo:
                start = start.replace(tzinfo=timezone.utc)
            dur = timedelta(hours=1)
            if dtend_iso:
                end = datetime.fromisoformat(dtend_iso)
                if not end.tzinfo:
                    end = end.replace(tzinfo=timezone.utc)
                dur = end - start
        except Exception:
            return instances

        parts = {}
        for part in rrule.split(';'):
            if '=' in part:
                k, v = part.split('=', 1)
                parts[k.strip()] = v.strip()

        freq = parts.get('FREQ', '')
        count = int(parts['COUNT']) if 'COUNT' in parts else None
        until = None
        if 'UNTIL' in parts:
            u = parts['UNTIL'].rstrip('Z')
            try:
                until = datetime.strptime(u[:15], '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
            except Exception:
                try:
                    until = datetime.strptime(u[:8], '%Y%m%d').replace(tzinfo=timezone.utc)
                except Exception:
                    pass

        interval = int(parts.get('INTERVAL', 1))

        # BYDAY for weekly recurrence: e.g. MO,WE,FR
        byDay = []
        if 'BYDAY' in parts:
            dayMap = {'MO':0,'TU':1,'WE':2,'TH':3,'FR':4,'SA':5,'SU':6}
            for d in parts['BYDAY'].split(','):
                d = d.strip()[-2:]
                if d in dayMap:
                    byDay.append(dayMap[d])

        cur = start
        i = 0
        maxIter = 2000
        while cur <= windowEnd and maxIter > 0:
            maxIter -= 1
            if until and cur > until:
                break
            if count is not None and i >= count:
                break

            candidates = []
            if freq == 'DAILY':
                candidates = [cur]
            elif freq == 'WEEKLY':
                if byDay:
                    # Generate all matching days in this week
                    weekStart = cur - timedelta(days=cur.weekday())
                    for wd in byDay:
                        cand = weekStart + timedelta(days=wd)
                        cand = cand.replace(hour=start.hour, minute=start.minute, second=start.second, tzinfo=start.tzinfo)
                        if cand >= start:
                            candidates.append(cand)
                    candidates.sort()
                else:
                    candidates = [cur]
            elif freq == 'MONTHLY':
                candidates = [cur]
            else:
                break  # unsupported freq

            for cand in candidates:
                if until and cand > until:
                    continue
                if count is not None and i >= count:
                    break
                if windowStart <= cand <= windowEnd:
                    endCand = cand + dur
                    instances.append({
                        "summary": summary,
                        "start": cand.strftime('%Y-%m-%d') if allDay else cand.isoformat(),
                        "end": endCand.strftime('%Y-%m-%d') if allDay else endCand.isoformat(),
                        "allDay": allDay
                    })
                i += 1

            # Advance to next occurrence
            if freq == 'DAILY':
                cur += timedelta(days=interval)
            elif freq == 'WEEKLY':
                if byDay:
                    # Jump to next week
                    cur += timedelta(weeks=interval)
                    cur = cur - timedelta(days=cur.weekday())  # back to Monday of that week
                else:
                    cur += timedelta(weeks=interval)
            elif freq == 'MONTHLY':
                month = cur.month + interval
                year = cur.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                try:
                    cur = cur.replace(year=year, month=month)
                except ValueError:
                    import calendar as _cal
                    lastDay = _cal.monthrange(year, month)[1]
                    cur = cur.replace(year=year, month=month, day=lastDay)
            else:
                break

        return instances

    events = []
    for block in _re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', raw, _re.DOTALL):
        def getField(name):
            m = _re.search(rf'^{name}(?:;[^:]+)?:(.+)$', block, _re.MULTILINE)
            return m.group(1).strip() if m else ''

        summary = getField('SUMMARY')
        if not summary:
            continue

        startIso, allDay, _ = parseDtLine(block, 'DTSTART')
        endIso, _, _         = parseDtLine(block, 'DTEND')
        if not startIso:
            continue

        rrule = getField('RRULE')
        if rrule:
            events.extend(expandRrule(rrule, startIso, allDay, summary, endIso))
        else:
            events.append({"summary": summary, "start": startIso, "end": endIso, "allDay": allDay})

    events.sort(key=lambda e: e["start"] or "")
    return events


def parseMultipartFile(headers, rfile):
    contentType = headers.get('Content-Type', '')
    length = int(headers.get('Content-Length', 0))
    body = rfile.read(length)
    m = re.search(r'boundary=([^\s;]+)', contentType)
    if not m:
        return None, None
    boundary = m.group(1).strip('"').encode()
    parts = body.split(b'--' + boundary)
    for part in parts[1:]:
        if part.strip() in (b'--', b''):
            break
        if b'\r\n\r\n' not in part:
            continue
        headerSection, fileData = part.split(b'\r\n\r\n', 1)
        fileData = fileData.rstrip(b'\r\n')
        headersStr = headerSection.decode('utf-8', errors='replace')
        filenameMatch = re.search(r'filename="([^"]+)"', headersStr)
        if filenameMatch:
            return filenameMatch.group(1), fileData
    return None, None


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

DROIDCAM_PORT = 4747
DROIDCAM_SIZE = "3840x2160"
_DROIDCAM_CACHE = {"host": None, "port": DROIDCAM_PORT, "time": 0.0}
_DROIDCAM_CACHE_TTL = 60


def _loadDroidcamConf():
    cfg = os.path.expanduser("~/.config/droidcam")
    ip, port = None, DROIDCAM_PORT
    try:
        with open(cfg) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ip="):
                    ip = line.split("=", 1)[1].strip() or None
                elif line.startswith("port="):
                    try:
                        port = int(line.split("=", 1)[1].strip())
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return ip, port


def _droidcamHost():
    """Return (host, port), resolving dynamically with subnet scan as fallback."""
    import time as _time

    now = _time.monotonic()
    if _DROIDCAM_CACHE["host"] and (now - _DROIDCAM_CACHE["time"]) < _DROIDCAM_CACHE_TTL:
        return _DROIDCAM_CACHE["host"], _DROIDCAM_CACHE["port"]

    conf_ip, conf_port = _loadDroidcamConf()
    host = conf_ip or "192.168.0.169"  # last-resort fallback

    # Try config IP first (fast path)
    try:
        sock = socket.create_connection((host, conf_port), timeout=1.0)
        sock.close()
        _DROIDCAM_CACHE["host"] = host
        _DROIDCAM_CACHE["port"] = conf_port
        _DROIDCAM_CACHE["time"] = now
        return host, conf_port
    except (OSError, socket.timeout):
        pass

    # Subnet scan
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "Scripts", "lib"))
        import droidcamScan
    except ImportError:
        droidcamScan = None

    if droidcamScan:
        result = droidcamScan.find_droidcam(host, conf_port)
        _DROIDCAM_CACHE["host"] = result[0]
        _DROIDCAM_CACHE["port"] = result[1]
        _DROIDCAM_CACHE["time"] = _time.monotonic()
        return result
    else:
        _DROIDCAM_CACHE["host"] = host
        _DROIDCAM_CACHE["port"] = conf_port
        _DROIDCAM_CACHE["time"] = now
        return host, conf_port


def _droidcamBase():
    host, port = _droidcamHost()
    return f"http://{host}:{port}"


def droidcamPut(path):
    """Send a PUT request to the droidcam HTTP API on the phone."""
    import urllib.request

    url = _droidcamBase() + path
    req = urllib.request.Request(url, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except Exception:
        return None


def getDroidcamInfo():
    import urllib.request

    try:
        with urllib.request.urlopen(_droidcamBase() + "/v1/camera/info", timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def getDroidcamState():
    # Check if droidcam-cli process is running
    out, code = run(["pgrep", "-x", "droidcam-cli"])
    connected = code == 0
    info = getDroidcamInfo() if connected else None
    host, port = _droidcamHost()
    return {
        "connected": connected,
        "host": f"{host}:{port}",
        "zmValue": info["zmValue"] if info else 1.0,
        "zmMin": info["zmMin"] if info else 1.0,
        "zmMax": info["zmMax"] if info else 6.0,
        "focusMode": info["focusMode"] if info else 0,
    }


def isDroidcamReachable():
    """Check if the phone is reachable and droidcam is listening before connecting."""
    try:
        host, port = _droidcamHost()
        sock = socket.create_connection((host, port), timeout=2)
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
        host, port = _droidcamHost()
        subprocess.Popen(
            ["droidcam-cli", "-size=" + DROIDCAM_SIZE, host, str(port)],
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
        p for pat in exts for p in glob.glob(os.path.join(WALLPAPER_DIR, pat))
    )
    if not images:
        return {"error": "No images found in wallpapers directory"}

    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}

    proc = subprocess.Popen(
        ["nsxiv", "-ot"] + images,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
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
_hwmonPath = None


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
    global _hwmonPath
    cpu = getCpuPercent()

    memInfo = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, val = line.split(":", 1)
            memInfo[key.strip()] = int(val.split()[0])  # kB
    ramTotal = memInfo.get("MemTotal", 1)
    ramUsed = ramTotal - memInfo.get("MemAvailable", 0)

    gpuUtil = vramUsed = vramTotal = 0
    gpuTemp = None

    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)

        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)

        powerDraw = pynvml.nvmlDeviceGetPowerUsage(handle)  # milliwatts
        powerMax = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle)  # milliwatts

        gpuUtil = (
            min(100, int(util.gpu * (powerDraw / powerMax))) if powerMax > 0 else 0
        )
        vramUsed = int(mem.used / 1024 / 1024)
        vramTotal = int(mem.total / 1024 / 1024)
        gpuTemp = int(
            pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        )

    except Exception:
        pass

    cpuTemp = None
    try:
        if _hwmonPath is None:
            import glob as _glob

            preferredLabels = ("Tccd1", "Tdie")
            candidates = {}  # label -> input path
            for namePath in _glob.glob("/sys/class/hwmon/hwmon*/name"):
                with open(namePath) as f:
                    if f.read().strip() != "k10temp":
                        continue
                hwmonDir = namePath.rsplit("/", 1)[0]
                for labelPath in _glob.glob(f"{hwmonDir}/temp*_label"):
                    with open(labelPath) as f:
                        label = f.read().strip()
                    if label in preferredLabels and label not in candidates:
                        candidates[label] = labelPath.replace("_label", "_input")
                break

            for label in preferredLabels:
                if label in candidates:
                    _hwmonPath = candidates[label]
                break

        if _hwmonPath:
            with open(_hwmonPath) as f:
                cpuTemp = round(int(f.read().strip()) / 1000)
    except Exception:
        pass

    return {
        "cpu": cpu,
        "ram": {"used": ramUsed, "total": ramTotal},  # kB
        "gpu": gpuUtil,
        "vram": {"used": vramUsed, "total": vramTotal},  # MiB
        "cpuTemp": cpuTemp,
        "gpuTemp": gpuTemp,
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
            # Any change event triggers a re-read; the lastSink guard below filters to actual default-sink swaps.
            if "'change'" in line:
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
        path = urlparse(self.path).path
        if path.startswith("/chat/"):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
        elif path.startswith("/status/") or path in ("/toggle/", "/media/", "/shopping/", "/eisenhower/", "/task/", "/obsidian/", "/droidcam/", "/bgremove/", "/webhook", "/reload", "/exit", "/parse/date", "/colors.css"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
        else:
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
            jsonResp(self, {"vpn": vpn, "sink": sink, "qwen": getQwenState()})
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
        elif path == "/status/diskhealth":
            healthFile = os.path.expanduser("~/.cache/dashboard/diskHealth.json")
            try:
                mtime = os.path.getmtime(healthFile)
                if time.time() - mtime > 1800:
                    jsonResp(self, {"error": "stale or missing", "lastUpdated": None})
                else:
                    with open(healthFile) as f:
                        jsonResp(self, json.load(f))
            except FileNotFoundError:
                jsonResp(self, {"error": "stale or missing", "lastUpdated": None})
        elif path == "/status/diskhealth/events":
            eventsFile = os.path.expanduser("~/.cache/dashboard/diskHealthEvents.json")
            try:
                with open(eventsFile) as f:
                    allEvents = json.load(f)
                pending = [e for e in allEvents if not e.get("acknowledged", False)]
                jsonResp(self, pending)
            except FileNotFoundError:
                jsonResp(self, [])
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
        elif path == "/chat":
            ChatRequestHandler(self, jsonResp).handleServeChatHtml()
        elif path == "/manifest.json":
            try:
                with open(os.path.join(os.path.dirname(__file__), "manifest.json"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_response(404)
                self.end_headers()
        elif path.startswith("/chat-icon-"):
            try:
                iconPath = os.path.join(os.path.dirname(__file__), os.path.basename(path))
                with open(iconPath, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
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
                self.send_header(
                    "Content-Type", "application/javascript; charset=utf-8"
                )
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
        elif path == "/wall":
            htmlPath = os.path.join(os.path.dirname(__file__), "wall.html")
            try:
                with open(htmlPath, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, "wall.html not found")

        elif path == "/wall/edit":
            htmlPath = os.path.join(os.path.dirname(__file__), "wall-edit.html")
            try:
                with open(htmlPath, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, "wall-edit.html not found")

        elif path == "/wall/layout":
            layout = getWallLayout()
            body = json.dumps(layout).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/wall/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = wallSubscribe()
            try:
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=30)
                        self.wfile.write(msg.encode())
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                wallUnsubscribe(q)

        elif path.startswith("/wall/uploads/"):
            filename = os.path.basename(path[len("/wall/uploads/"):])
            filePath = os.path.join(_wallUploadsDir, filename)
            if not os.path.exists(filePath):
                self.send_error(404)
                return
            ext = filename.rsplit(".", 1)[-1].lower()
            mimeMap = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
            mime = mimeMap.get(ext, "application/octet-stream")
            with open(filePath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path.startswith("/wall/ics"):
            from urllib.parse import urlparse as _urlparse, parse_qs, unquote
            qs = parse_qs(_urlparse(self.path).query)
            icsUrl = qs.get("url", [""])[0]
            icsUrl = unquote(icsUrl)
            if not icsUrl:
                self.send_error(400, "Missing url parameter")
                return
            events = fetchIcs(icsUrl)
            body = json.dumps(events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path.startswith("/wall/list/todoist"):
            from urllib.parse import urlparse as _up2, parse_qs as _pqs2
            qs2 = _pqs2(_up2(self.path).query)
            filterStr = qs2.get("filter", [""])[0]
            projectName = qs2.get("project", [""])[0]
            limit = int(qs2.get("limit", ["50"])[0])
            tasks = getWallTodoistTasks(filterStr, projectName, limit)
            body = json.dumps(tasks).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path.startswith("/wall/list/obsidian"):
            from urllib.parse import urlparse as _up3, parse_qs as _pqs3, unquote as _uq3
            qs3 = _pqs3(_up3(self.path).query)
            relPath = _uq3(qs3.get("file", [""])[0])
            filterMode = qs3.get("filter", ["incomplete"])[0]
            limit = int(qs3.get("limit", ["100"])[0])
            if not relPath:
                self.send_error(400, "Missing file parameter")
                return
            tasks = getWallObsidianTasks(relPath, filterMode, limit)
            body = json.dumps(tasks).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/shopping/items":
            jsonResp(self, getShoppingListItems())
        elif path == "/chat/sessions":
            ChatRequestHandler(self, jsonResp).handleGetSessions()
        elif path.startswith("/chat/sessions/") and path.endswith("/history"):
            sessionId = path[len("/chat/sessions/"):-len("/history")]
            ChatRequestHandler(self, jsonResp).handleGetHistory(sessionId)
        elif path.startswith("/chat/sessions/") and path.endswith("/stream"):
            prefix = "/chat/sessions/"
            suffix = "/stream"
            middle = path[len(prefix):-len(suffix)]
            parts = middle.split("/messages/")
            if len(parts) == 2:
                ChatRequestHandler(self, jsonResp).handleGetStream(parts[0], parts[1])
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/diskhealth/events/ack":
            eventsFile = os.path.expanduser("~/.cache/dashboard/diskHealthEvents.json")
            try:
                with open(eventsFile) as f:
                    allEvents = json.load(f)
                for e in allEvents:
                    e["acknowledged"] = True
                tmpPath = eventsFile + ".tmp"
                with open(tmpPath, "w") as f:
                    json.dump(allEvents, f)
                os.replace(tmpPath, eventsFile)
            except FileNotFoundError:
                pass
            jsonResp(self, {"ok": True})
        elif path == "/toggle/vpn":
            toggleVpn()
            jsonResp(self, {"ok": True})
        elif path == "/toggle/sink":
            cycleSink()
            jsonResp(self, {"ok": True})
        elif path == "/toggle/qwen":
            toggleQwen()
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
        elif path == "/wall/layout":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                saveWallLayout(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        elif path == "/wall/upload":
            import uuid as uuidMod
            os.makedirs(_wallUploadsDir, exist_ok=True)
            contentType = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in contentType:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"Expected multipart/form-data"}')
                return
            filename, fileData = parseMultipartFile(self.headers, self.rfile)
            if not filename or fileData is None:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"No file found in upload"}')
                return
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
            safeExt = ext if ext in ("png", "jpg", "jpeg", "gif", "webp") else "png"
            newName = uuidMod.uuid4().hex + "." + safeExt
            destPath = os.path.join(_wallUploadsDir, newName)
            with open(destPath, "wb") as f:
                f.write(fileData)
            url = "/wall/uploads/" + newName
            respBody = json.dumps({"url": url}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(respBody)))
            self.end_headers()
            self.wfile.write(respBody)
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
        elif path == "/task/create":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            try:
                line = createTask(
                    body.get("text", ""),
                    due=body.get("due"),
                    priority=body.get("priority"),
                    domain=body.get("domain"),
                    desc=body.get("desc"),
                )
                jsonResp(self, {"ok": True, "line": line})
            except Exception as e:
                jsonResp(self, {"ok": False, "error": str(e)}, 500)
        elif path == "/parse/date":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            resolved = resolveDueDate(body.get("date", ""))
            jsonResp(self, {"date": resolved or None})
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
        elif path == "/chat/sessions":
            ChatRequestHandler(self, jsonResp).handlePostCreateSession()
        elif path.startswith("/chat/sessions/") and path.endswith("/message"):
            sessionId = path[len("/chat/sessions/"):-len("/message")]
            ChatRequestHandler(self, jsonResp).handlePostMessage(sessionId)
        elif path.startswith("/chat/sessions/") and path.endswith("/permission"):
            sessionId = path[len("/chat/sessions/"):-len("/permission")]
            ChatRequestHandler(self, jsonResp).handlePostPermission(sessionId)
        elif path.startswith("/chat/sessions/") and "/messages/" in path and path.endswith("/cancel"):
            prefix = "/chat/sessions/"
            suffix = "/cancel"
            middle = path[len(prefix):-len(suffix)]
            parts = middle.split("/messages/")
            if len(parts) == 2:
                ChatRequestHandler(self, jsonResp).handlePostCancel(parts[0], parts[1])
        elif path == "/chat/auth":
            ChatRequestHandler(self, jsonResp).handlePostAuth()
        elif path == "/chat/register":
            ChatRequestHandler(self, jsonResp).handlePostRegister()
        elif path == "/chat/change-password":
            ChatRequestHandler(self, jsonResp).handlePostChangePassword()
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

    def diskHealthLoop():
        # Warm cache immediately, then refresh every 15 min
        while True:
            try:
                refreshDiskHealth()
            except Exception as e:
                print(f"diskHealthLoop error: {e}", file=sys.stderr)
            time.sleep(900)

    diskHealthThread = threading.Thread(target=diskHealthLoop, daemon=True)
    diskHealthThread.start()

    os.makedirs(_wallUploadsDir, exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Dashboard server running on port {PORT}")
    server.serve_forever()
