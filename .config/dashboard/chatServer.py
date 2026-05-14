#!/usr/bin/env python3
"""
chatServer.py
Chat subsystem for the AwesomeWM dashboard HTTP server.

Handles sessions, message history, and streaming responses
for qwen and claude models via SSE (Server-Sent Events).

Config: ~/.config/dashboard/chat.conf  (ntfy_topic, auth_token)
DB:     ~/.config/dashboard/chat.db
"""

import json
import subprocess
import os
import sys
import time
import sqlite3
import uuid
import threading
import configparser
import requests
import select
import fcntl
import re
import signal
import errno
import hashlib
import hmac
import queue as _queue

CHAT_CONFIG_PATH = os.path.expanduser("~/.config/dashboard/chat.conf")
CHAT_DB_PATH = os.path.expanduser("~/.config/dashboard/chat.db")
CHAT_USERS_DB_PATH = os.path.expanduser("~/.config/dashboard/chat_users.db")

CHAT_AUTH_SECRET = os.environ.get("CHAT_AUTH_SECRET", "")
if not CHAT_AUTH_SECRET:
    _secret_path = os.path.expanduser("~/.config/dashboard/chat_auth_secret")
    try:
        with open(_secret_path) as f:
            CHAT_AUTH_SECRET = f.read().strip()
    except FileNotFoundError:
        CHAT_AUTH_SECRET = str(uuid.uuid4())
        with open(_secret_path, "w") as f:
            f.write(CHAT_AUTH_SECRET)

# Regex for ANSI escape sequences
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')



def loadChatConfig():
    config = configparser.ConfigParser()
    with open(CHAT_CONFIG_PATH) as f:
        config.read_string("[chat]\n" + f.read())
    return {"ntfyTopic": config["chat"].get("ntfy_topic", ""), "authToken": config["chat"].get("auth_token", "")}


CHAT_CONFIG = loadChatConfig()


def persistMessageEvent(conn, messageId, seq, eventType, payload):
    payloadJson = json.dumps(payload)
    createdAt = int(time.time() * 1000)
    conn.execute("INSERT INTO messageEvents (messageId, seq, type, payload, createdAt) VALUES (?, ?, ?, ?, ?)",
                 (messageId, seq, eventType, payloadJson, createdAt))
    conn.commit()


class ActiveStream:
    """Per-message pub/sub state. Owned by the producer thread; subscribers attach via attach()."""
    def __init__(self, messageId):
        self.messageId = messageId
        self.subscribers = []
        self.lock = threading.Lock()
        self.lastCommittedSeq = 0
        self.status = 'streaming'
        self.proc = None
        self.cancelRequested = False

    def setProc(self, proc):
        with self.lock:
            self.proc = proc

    def requestCancel(self):
        """Mark cancel requested and SIGTERM the subprocess if any. Returns True if a proc was signaled."""
        with self.lock:
            self.cancelRequested = True
            proc = self.proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            return True
        return False

    def attach(self):
        q = _queue.Queue()
        with self.lock:
            self.subscribers.append(q)
            return q, self.lastCommittedSeq

    def detach(self, q):
        with self.lock:
            try:
                self.subscribers.remove(q)
            except ValueError:
                pass

    def fanout(self, payload):
        with self.lock:
            dead = []
            for q in self.subscribers:
                try:
                    q.put_nowait(payload)
                except Exception:
                    dead.append(q)
            for q in dead:
                try:
                    self.subscribers.remove(q)
                except ValueError:
                    pass

    def close(self, finalStatus):
        with self.lock:
            self.status = finalStatus
        self.fanout({'kind': 'status', 'status': finalStatus})
        with self.lock:
            for q in self.subscribers:
                try:
                    q.put_nowait(None)
                except Exception:
                    pass
            self.subscribers = []


activeStreams = {}
activeStreamsLock = threading.Lock()


def getOrCreateActiveStream(messageId):
    with activeStreamsLock:
        s = activeStreams.get(messageId)
        if s is None:
            s = ActiveStream(messageId)
            activeStreams[messageId] = s
        return s


def getActiveStream(messageId):
    with activeStreamsLock:
        return activeStreams.get(messageId)


def removeActiveStream(messageId):
    with activeStreamsLock:
        activeStreams.pop(messageId, None)


def initChatDb():
    conn = sqlite3.connect(CHAT_DB_PATH)
    hasTable = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='messageEvents'").fetchone()
    if not hasTable:
        conn.close()
        if os.path.exists(CHAT_DB_PATH):
            os.remove(CHAT_DB_PATH)
        conn = sqlite3.connect(CHAT_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            title TEXT,
            createdAt INTEGER NOT NULL,
            opcodeSessionId TEXT,
            owner TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            sessionId TEXT NOT NULL,
            role TEXT NOT NULL,
            createdAt INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'complete'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messageEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            messageId TEXT NOT NULL,
            seq INTEGER NOT NULL,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            createdAt INTEGER NOT NULL,
            UNIQUE(messageId, seq)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idxMessageEventsMessageSeq ON messageEvents(messageId, seq)")
    conn.execute("CREATE INDEX IF NOT EXISTS idxMessagesSession ON messages(sessionId, createdAt)")
    conn.commit()
    conn.close()


initChatDb()

# Enable WAL mode for concurrent reader/writer access
try:
    _walConn = sqlite3.connect(CHAT_DB_PATH)
    _walConn.execute("PRAGMA journal_mode=WAL")
    _walConn.close()
except Exception:
    pass


def initUsersDb():
    conn = sqlite3.connect(CHAT_USERS_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            expiresAt INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


initUsersDb()


def _hashPassword(password, salt=None):
    if salt is None:
        salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${h}"


def _verifyPassword(password, stored):
    parts = stored.split("$", 1)
    if len(parts) != 2:
        return False
    salt, h = parts
    return hmac.compare_digest(_hashPassword(password, salt), stored)


def _generateToken(username):
    payload = f"{username}:{int(time.time())}"
    sig = hmac.new(CHAT_AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verifyToken(token):
    parts = token.split(".", 2)
    if len(parts) != 2:
        return None
    payload, sig = parts
    expected_sig = hmac.new(CHAT_AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    parts2 = payload.split(":", 1)
    if len(parts2) != 2:
        return None
    username, ts = parts2
    if int(ts) < time.time() - 2592000:
        return None
    return username


def _createUserIfNotExists(username, password, role="user"):
    conn = sqlite3.connect(CHAT_USERS_DB_PATH)
    try:
        existing = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            conn.close()
            return False
        pw_hash = _hashPassword(password)
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                     (username, pw_hash, role))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        conn.close()
        return False


def _ensureAdminExists():
    adminPath = os.path.expanduser("~/.config/dashboard/chat_admin_setup")
    if os.path.exists(adminPath):
        return
    conn = sqlite3.connect(CHAT_USERS_DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    if count == 0:
        admin_user = "admin"
        admin_pass = os.environ.get("CHAT_ADMIN_PASSWORD", "changeme")
        _createUserIfNotExists(admin_user, admin_pass, "admin")
    with open(adminPath, "w") as f:
        f.write("done")


_ensureAdminExists()

for _u in ("Taylor", "Jim", "Nicole", "Janett", "Sami"):
    _createUserIfNotExists(_u, "password")


def _stripAnsi(text):
    return ANSI_RE.sub('', text)


class ChatRequestHandler:
    """Handles all HTTP request I/O for chat endpoints.

    Receives the main BaseHTTPRequestHandler instance and performs auth,
    DB queries, and SSE streaming directly on it.
    """

    def __init__(self, mainHandler, jsonResp):
        self.handler = mainHandler
        self.jsonResp = jsonResp
        self.user = None
        self.userRole = None

    def _checkAuth(self):
        authHeader = self.handler.headers.get("Authorization", "")
        if not authHeader.startswith("Bearer "):
            self.jsonResp(self.handler, {"error": "unauthorized"}, 401)
            return False
        token = authHeader[7:]
        # Check legacy single-token auth
        if token == CHAT_CONFIG.get("authToken", ""):
            self.user = "admin"
            self.userRole = "admin"
            return True
        # Check per-user token
        username = _verifyToken(token)
        if not username:
            self.jsonResp(self.handler, {"error": "unauthorized"}, 401)
            return False
        conn = sqlite3.connect(CHAT_USERS_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if not row:
            self.jsonResp(self.handler, {"error": "unauthorized"}, 401)
            return False
        self.user = username
        self.userRole = row["role"]
        return True

    def _getChatDb(self):
        conn = sqlite3.connect(CHAT_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _readBody(self):
        length = int(self.handler.headers.get("Content-Length", 0))
        raw = self.handler.rfile.read(length)
        return json.loads(raw) if raw else {}

    # ── GET handlers ───────────────────────────────────────────────────────

    def handleGetSessions(self):
        if not self._checkAuth():
            return
        conn = self._getChatDb()
        if self.userRole == "admin":
            rows = conn.execute("SELECT id, model, title, createdAt FROM sessions ORDER BY createdAt DESC").fetchall()
        else:
            rows = conn.execute("SELECT id, model, title, createdAt FROM sessions WHERE owner=? ORDER BY createdAt DESC", (self.user,)).fetchall()
        conn.close()
        self.jsonResp(self.handler, [{"id": r["id"], "model": r["model"], "title": r["title"], "createdAt": r["createdAt"]} for r in rows])

    def handleGetHistory(self, sessionId):
        if not self._checkAuth():
            return
        conn = self._getChatDb()
        sessionRow = conn.execute("SELECT owner FROM sessions WHERE id=?", (sessionId,)).fetchone()
        if not sessionRow:
            conn.close()
            self.jsonResp(self.handler, {"error": "session not found"}, 404)
            return
        if self.userRole != "admin" and sessionRow["owner"] != self.user:
            conn.close()
            self.jsonResp(self.handler, {"error": "forbidden"}, 403)
            return
        rows = conn.execute("SELECT id, role, createdAt, status, rowid FROM messages WHERE sessionId=? ORDER BY createdAt ASC", (sessionId,)).fetchall()
        result = []
        for msg in rows:
            evtRows = conn.execute("SELECT seq, type, payload FROM messageEvents WHERE messageId=? ORDER BY seq ASC", (msg["id"],)).fetchall()
            events = []
            content = ""
            msgStatus = msg["status"]
            toolResultMap = {}
            for i, evt in enumerate(evtRows):
                evtPayload = json.loads(evt["payload"])
                if evt["type"] == "toolResult":
                    toolResultMap[evtPayload.get("seq", 0)] = evtPayload.get("output", "")
            toolResultSeq = 0
            for evt in evtRows:
                evtPayload = json.loads(evt["payload"])
                evtSeq = evt["seq"]
                if evt["type"] == "thinking":
                    events.append({"type": "thinking", "content": evtPayload.get("content", ""), "seq": evtSeq})
                elif evt["type"] == "text":
                    events.append({"type": "text", "content": evtPayload.get("content", ""), "seq": evtSeq})
                    content += evtPayload.get("content", "")
                elif evt["type"] == "tool":
                    toolResultSeq += 1
                    output = toolResultMap.get(toolResultSeq, "")
                    events.append({"type": "tool", "name": evtPayload.get("name", evtPayload.get("tool", "")), "input": json.dumps(evtPayload.get("input", {})), "output": output, "seq": evtSeq})
                elif evt["type"] == "error":
                    events.append({"type": "error", "content": evtPayload.get("reason", ""), "seq": evtSeq})
                elif evt["type"] == "done":
                    pass
            isComplete = 1 if msgStatus in ("complete", "canceled", "error") else 0
            result.append({"id": msg["id"], "role": msg["role"], "content": content, "createdAt": msg["createdAt"], "events": json.dumps(events), "isComplete": isComplete, "status": msgStatus})
        conn.close()
        self.jsonResp(self.handler, result)

    def handleGetStream(self, sessionId, messageId):
        if not self._checkAuth():
            return
        conn = self._getChatDb()
        sessionRow = conn.execute("SELECT owner FROM sessions WHERE id=?", (sessionId,)).fetchone()
        if not sessionRow:
            conn.close()
            self.jsonResp(self.handler, {"error": "session not found"}, 404)
            return
        if self.userRole != "admin" and sessionRow["owner"] != self.user:
            conn.close()
            self.jsonResp(self.handler, {"error": "forbidden"}, 403)
            return
        msgRow = conn.execute("SELECT id, status FROM messages WHERE id=? AND sessionId=?", (messageId, sessionId)).fetchone()
        if not msgRow:
            conn.close()
            self.jsonResp(self.handler, {"error": "message not found"}, 404)
            return
        msgStatus = msgRow["status"]
        conn.close()

        fullPath = self.handler.path
        sinceSeq = 0
        if "?" in fullPath:
            qsPart = fullPath.split("?", 1)[1]
            for param in qsPart.split("&"):
                if param.startswith("sinceSeq="):
                    try:
                        sinceSeq = int(param.split("=", 1)[1])
                        if sinceSeq < 0:
                            sinceSeq = 0
                    except ValueError:
                        sinceSeq = 0

        h = self.handler
        h.is_sse_stream = True
        h.send_response(200)
        h.send_header("Content-Type", "text/event-stream")
        h.send_header("Cache-Control", "no-cache")
        h.send_header("X-Accel-Buffering", "no")
        h.send_header("Connection", "close")
        h.end_headers()

        def _sseWrite(obj):
            try:
                h.wfile.write(f'data: {json.dumps(obj, separators=(",", ":"))}\n\n'.encode())
                h.wfile.flush()
            except OSError:
                return False
            return True

        stream = getActiveStream(messageId)
        subscriberQ = None
        try:
            if stream is None:
                replayConn = sqlite3.connect(CHAT_DB_PATH)
                replayConn.row_factory = sqlite3.Row
                evtRows = replayConn.execute(
                    "SELECT seq, type, payload FROM messageEvents WHERE messageId=? AND seq > ? AND type != 'done' ORDER BY seq ASC",
                    (messageId, sinceSeq)
                ).fetchall()
                for evt in evtRows:
                    payloadObj = json.loads(evt["payload"])
                    if not _sseWrite({'kind': 'committed', 'seq': evt["seq"], 'type': evt["type"], 'payload': payloadObj}):
                        return
                replayConn.close()
                _sseWrite({'kind': 'status', 'status': msgStatus})
            else:
                subscriberQ, snapshotSeq = stream.attach()
                # If stream was already closed before we attached, send status and exit
                with stream.lock:
                    st = stream.status
                if st != 'streaming':
                    replayConn = sqlite3.connect(CHAT_DB_PATH)
                    replayConn.row_factory = sqlite3.Row
                    upperBound = max(snapshotSeq, sinceSeq)
                    evtRows = replayConn.execute(
                        "SELECT seq, type, payload FROM messageEvents WHERE messageId=? AND seq > ? AND seq <= ? AND type != 'done' ORDER BY seq ASC",
                        (messageId, sinceSeq, upperBound)
                    ).fetchall()
                    for evt in evtRows:
                        payloadObj = json.loads(evt["payload"])
                        if not _sseWrite({'kind': 'committed', 'seq': evt["seq"], 'type': evt["type"], 'payload': payloadObj}):
                            replayConn.close()
                            return
                    replayConn.close()
                    _sseWrite({'kind': 'status', 'status': st})
                    stream.detach(subscriberQ)
                    _sseWrite({'kind': 'closed'})
                    return

                replayConn = sqlite3.connect(CHAT_DB_PATH)
                replayConn.row_factory = sqlite3.Row
                upperBound = max(snapshotSeq, sinceSeq)
                evtRows = replayConn.execute(
                    "SELECT seq, type, payload FROM messageEvents WHERE messageId=? AND seq > ? AND seq <= ? AND type != 'done' ORDER BY seq ASC",
                    (messageId, sinceSeq, upperBound)
                ).fetchall()
                maxReplayedSeq = sinceSeq
                for evt in evtRows:
                    if evt["seq"] > maxReplayedSeq:
                        maxReplayedSeq = evt["seq"]
                    payloadObj = json.loads(evt["payload"])
                    _sseWrite({'kind': 'committed', 'seq': evt["seq"], 'type': evt["type"], 'payload': payloadObj})
                replayConn.close()

                while True:
                    try:
                        item = subscriberQ.get(timeout=15)
                    except Exception:
                        _sseWrite({'kind': '_keepalive'})
                        continue
                    if item is None:
                        break
                    if item.get('kind') == 'committed' and item.get('seq', 0) <= maxReplayedSeq:
                        continue
                    if not _sseWrite(item):
                        return

            _sseWrite({'kind': 'closed'})
        finally:
            if subscriberQ is not None and stream is not None:
                stream.detach(subscriberQ)

    def handleServeChatHtml(self):
        try:
            htmlPath = os.path.join(os.path.dirname(__file__), "chat.html")
            with open(htmlPath, "rb") as f:
                body = f.read()
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "text/html; charset=utf-8")
            self.handler.send_header("Content-Length", len(body))
            self.handler.end_headers()
            self.handler.wfile.write(body)
        except Exception as e:
            self.jsonResp(self.handler, {"error": str(e)}, 500)

    # ── POST handlers ──────────────────────────────────────────────────────

    def handlePostCreateSession(self):
        if not self._checkAuth():
            return
        body = self._readBody()
        model = body.get("model", "")
        if model not in ("qwen", "claude", "llama"):
            self.jsonResp(self.handler, {"error": "invalid model"}, 400)
            return
        if self.userRole != "admin" and model != "llama":
            self.jsonResp(self.handler, {"error": "forbidden"}, 403)
            return
        sessionId = str(uuid.uuid4())
        conn = self._getChatDb()
        conn.execute("INSERT INTO sessions (id, model, title, createdAt, owner) VALUES (?, ?, ?, ?, ?)",
                      (sessionId, model, None, int(time.time()), self.user))
        conn.commit()
        conn.close()
        self.jsonResp(self.handler, {"id": sessionId, "model": model, "createdAt": int(time.time())})

    def handlePostMessage(self, sessionId):
        if not self._checkAuth():
            return
        if self.userRole != "admin":
            sessionRow = self._getChatDb().execute("SELECT owner FROM sessions WHERE id=?", (sessionId,)).fetchone()
            if not sessionRow or sessionRow["owner"] != self.user:
                self._getChatDb().close()
                self.jsonResp(self.handler, {"error": "forbidden"}, 403)
                return
        body = self._readBody()
        content = body.get("content", "")
        conn = self._getChatDb()
        modelRow = conn.execute("SELECT model FROM sessions WHERE id=?", (sessionId,)).fetchone()
        if not modelRow:
            conn.close()
            self.jsonResp(self.handler, {"error": "session not found"}, 404)
            return
        model = modelRow["model"]

        # Finalize any stale pending assistant message from a previous disconnected turn
        conn.execute("UPDATE messages SET status='complete' WHERE sessionId=? AND role='assistant' AND status='streaming'", (sessionId,))
        conn.commit()

        # Insert user message first (so it sorts before assistant in ORDER BY createdAt ASC)
        userMsgId = str(uuid.uuid4())
        userCreatedAt = int(time.time())
        conn.execute("INSERT INTO messages (id, sessionId, role, createdAt, status) VALUES (?, ?, ?, ?, ?)",
                      (userMsgId, sessionId, "user", userCreatedAt, "complete"))
        conn.commit()

        # Insert assistant message with a slightly later timestamp
        assistantMsgId = str(uuid.uuid4())
        conn.execute("INSERT INTO messages (id, sessionId, role, createdAt, status) VALUES (?, ?, ?, ?, ?)",
                      (assistantMsgId, sessionId, "assistant", userCreatedAt + 1, "streaming"))
        conn.commit()

        stream = getOrCreateActiveStream(assistantMsgId)
        persistMessageEvent(conn, userMsgId, 1, "text", {"content": content})
        conn.close()

        threading.Thread(target=self._streamToSse, args=(sessionId, model, content, assistantMsgId, userMsgId, stream), daemon=True).start()
        self.jsonResp(self.handler, {"userMessageId": userMsgId, "assistantMessageId": assistantMsgId}, 202)

    def _streamToSse(self, sessionId, model, content, assistantMsgId, userMsgId, stream):
        """Background thread: finalize the DB after the subprocess exits."""
        conn = sqlite3.connect(CHAT_DB_PATH)
        seq = 0
        timedOut = False
        finalStatus = "complete"
        try:
            if model == "qwen":
                fullResponse, seq, timedOut = self._handleQwenWithSse(sessionId, content, assistantMsgId, conn, stream)
            elif model == "claude":
                fullResponse, seq, timedOut = self._handleClaudeWithSse(sessionId, content, assistantMsgId, conn, stream)
            elif model == "llama":
                fullResponse, seq, timedOut = self._handleLlamaWithSse(sessionId, content, assistantMsgId, conn, stream)
            else:
                fullResponse, seq, timedOut = "", 0, False

            persistMessageEvent(conn, assistantMsgId, seq, "done", {})
            wasCanceled = False
            with stream.lock:
                wasCanceled = stream.cancelRequested
            if wasCanceled:
                seq += 1
                persistMessageEvent(conn, assistantMsgId, seq, "error", {"reason": "canceled"})
                stream.lastCommittedSeq = seq
                stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'error', 'payload': {'reason': 'canceled'}})
                conn.execute("UPDATE messages SET status='canceled' WHERE id=?", (assistantMsgId,))
                conn.commit()
                stream.close('canceled')
            else:
                finalStatus = "error" if timedOut else "complete"
                conn.execute("UPDATE messages SET status=? WHERE id=?", (finalStatus, assistantMsgId))
                conn.commit()
                stream.close(finalStatus)
            removeActiveStream(assistantMsgId)

        except Exception as e:
            finalStatus = "error"
            try:
                persistMessageEvent(conn, assistantMsgId, seq, "error", {"reason": str(e)[:200]})
                conn.execute("UPDATE messages SET status='error' WHERE id=?", (assistantMsgId,))
                conn.commit()
                stream.close("error")
                removeActiveStream(assistantMsgId)
            except Exception:
                pass
        finally:
            if CHAT_CONFIG.get("ntfyTopic"):
                threading.Thread(target=self._notifyNtfy, args=(CHAT_CONFIG["ntfyTopic"],), daemon=True).start()

    def _handleQwenWithSse(self, sessionId, content, assistantMsgId, conn, stream):
        """Handle a qwen chat request using PTY."""
        conn2 = sqlite3.connect(CHAT_DB_PATH)
        conn2.row_factory = sqlite3.Row
        opcodeRow = conn2.execute("SELECT opcodeSessionId FROM sessions WHERE id=?", (sessionId,)).fetchone()
        opcodeSessionId = opcodeRow["opcodeSessionId"] if opcodeRow and opcodeRow["opcodeSessionId"] else None
        conn2.close()

        if opcodeSessionId:
            cmd = ["opencode", "run", "--session", opcodeSessionId, "--format", "json", "--thinking", content]
        else:
            cmd = ["opencode", "run", "--model", "local-server/qwen", "--format", "json", "--thinking", "--dir", "/home/max/dotfiles", content]

        return self._runQwenWithPty(cmd, sessionId, assistantMsgId, conn, stream)

    def _runQwenWithPty(self, cmd, sessionId, assistantMsgId, conn, stream):
        """Run opencode with a PTY, streaming JSON events."""
        master_fd = None
        slave_fd = None
        proc = None
        timedOut = False
        seq = 0
        pendingThinking = ""
        pendingText = ""
        try:
            master_fd, slave_fd = os.openpty()

            # Set non-blocking on the master fd
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                pass_fds=[slave_fd],
            )
            os.close(slave_fd)
            slave_fd = None
            stream.setProc(proc)

            capturedSessionId = None
            buffer = ""
            conn2 = sqlite3.connect(CHAT_DB_PATH)
            conn2.row_factory = sqlite3.Row
            procTimeout = 600  # 10-minute total timeout
            startTime = time.time()
            idleSince = time.time()
            idleMax = 120  # 2-minute idle = opencode stalled

            while True:
                elapsed = time.time() - startTime
                if elapsed > procTimeout:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    timedOut = True
                    break

                poll = proc.poll()
                if poll is not None:
                    break

                if stream.cancelRequested:
                    break

                try:
                    rlist, _, xlist = select.select([master_fd], [], [master_fd], 5.0)
                except (OSError, ValueError):
                    break

                if xlist:
                    break

                if not rlist:
                    # No data + process still alive
                    if time.time() - idleSince > idleMax:
                        # Opencode stalled — kill it
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        timedOut = True
                        break
                    continue

                idleSince = time.time()

                try:
                    data = os.read(master_fd, 8192)
                except OSError:
                    break

                if not data:
                    break

                text = data.decode('utf-8', errors='replace')
                buffer += str(text)

                # Process buffer line by line
                lines = buffer.split('\n')
                buffer = lines[-1]  # Keep incomplete last line

                for line in lines[:-1]:
                    cleanLine = _stripAnsi(line).strip()
                    if not cleanLine:
                        continue

                    event = None
                    try:
                        event = json.loads(cleanLine)
                    except json.JSONDecodeError:
                        pass

                    if event is None:
                        continue

                    if capturedSessionId is None and "sessionID" in event:
                        capturedSessionId = event["sessionID"]
                        conn2.execute("UPDATE sessions SET opcodeSessionId=? WHERE id=?", (capturedSessionId, sessionId))
                        conn2.commit()

                    eType = event.get("type")
                    part = event.get("part", {})

                    if eType == "text":
                        textContent = part.get("text", "")
                        if textContent:
                            if pendingThinking:
                                seq += 1
                                thinkingPayload = {"content": pendingThinking}
                                persistMessageEvent(conn2, assistantMsgId, seq, "thinking", thinkingPayload)
                                stream.lastCommittedSeq = seq
                                stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'thinking', 'payload': thinkingPayload})
                                pendingThinking = ""
                            pendingText += textContent
                            stream.fanout({'kind': 'delta', 'blockIndex': seq + 1, 'blockType': 'text', 'textChunk': textContent})

                    elif eType == "reasoning":
                        textContent = part.get("text", "")
                        if textContent:
                            if pendingText:
                                seq += 1
                                textPayload = {"content": pendingText}
                                persistMessageEvent(conn2, assistantMsgId, seq, "text", textPayload)
                                stream.lastCommittedSeq = seq
                                stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'text', 'payload': textPayload})
                                pendingText = ""
                            pendingThinking += textContent
                            stream.fanout({'kind': 'delta', 'blockIndex': seq + 1, 'blockType': 'thinking', 'textChunk': textContent})

                    elif eType == "tool_use":
                        if pendingThinking:
                            seq += 1
                            thinkingPayload = {"content": pendingThinking}
                            persistMessageEvent(conn2, assistantMsgId, seq, "thinking", thinkingPayload)
                            stream.lastCommittedSeq = seq
                            stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'thinking', 'payload': thinkingPayload})
                            pendingThinking = ""
                        if pendingText:
                            seq += 1
                            textPayload = {"content": pendingText}
                            persistMessageEvent(conn2, assistantMsgId, seq, "text", textPayload)
                            stream.lastCommittedSeq = seq
                            stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'text', 'payload': textPayload})
                            pendingText = ""
                        toolPayload = {"name": part.get("tool", ""), "input": part.get("input", {})}
                        seq += 1
                        persistMessageEvent(conn2, assistantMsgId, seq, "tool", toolPayload)
                        stream.lastCommittedSeq = seq
                        stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'tool', 'payload': toolPayload})

            if pendingThinking:
                seq += 1
                thinkingPayload = {"content": pendingThinking}
                persistMessageEvent(conn2, assistantMsgId, seq, "thinking", thinkingPayload)
                stream.lastCommittedSeq = seq
                stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'thinking', 'payload': thinkingPayload})
            if pendingText:
                seq += 1
                textPayload = {"content": pendingText}
                persistMessageEvent(conn2, assistantMsgId, seq, "text", textPayload)
                stream.lastCommittedSeq = seq
                stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'text', 'payload': textPayload})

            if timedOut:
                errorPayload = {"reason": "timeout"}
                persistMessageEvent(conn2, assistantMsgId, seq, "error", errorPayload)
                stream.lastCommittedSeq = seq
                stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'error', 'payload': errorPayload})

            # Wait for process with timeout
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            conn2.close()
            return pendingText, seq, timedOut

        finally:
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait()
                except Exception:
                    pass

    def _handleClaudeWithSse(self, sessionId, content, assistantMsgId, conn, stream):
        conn2 = sqlite3.connect(CHAT_DB_PATH)
        conn2.row_factory = sqlite3.Row
        priorMessages = conn2.execute("SELECT id, role, content, createdAt FROM messages WHERE sessionId=? ORDER BY createdAt ASC", (sessionId,)).fetchall()
        conn2.close()

        historyLines = []
        for msg in priorMessages:
            roleLabel = "Human" if msg["role"] == "user" else "Assistant"
            historyLines.append(f"{roleLabel}: {msg['content']}")
        historyStr = "\n\n".join(historyLines)
        fullPrompt = f"<prior_conversation>\n{historyStr}\n</prior_conversation>\n\nHuman: {content}" if historyStr else content

        proc = subprocess.Popen(
            ["timeout", "300", "/home/max/.local/bin/claude", "--print", "--verbose", "--output-format", "stream-json", fullPrompt],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        seq = 0
        fullResponse = ""

        for line in proc.stdout:  # type: ignore[union-attr]
            if stream.cancelRequested:
                break
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = ""
            if obj.get("type") == "assistant":
                try:
                    text = obj["message"]["content"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    pass
                # Extract tool_use blocks from assistant messages
                for block in obj.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use":
                        toolPayload = {"name": block.get("name", ""), "input": block.get("input", {})}
                        seq += 1
                        persistMessageEvent(conn, assistantMsgId, seq, "tool", toolPayload)
                        stream.lastCommittedSeq = seq
                        stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'tool', 'payload': toolPayload})
            elif obj.get("type") == "content_block_delta":
                try:
                    text = obj["delta"]["text"]
                except (KeyError, TypeError):
                    pass
            if text:
                fullResponse += text
                seq += 1
                persistMessageEvent(conn, assistantMsgId, seq, "text", {"content": text})
                stream.lastCommittedSeq = seq
                stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'text', 'payload': {'content': text}})
                stream.fanout({'kind': 'delta', 'blockIndex': seq, 'blockType': 'text', 'textChunk': text})
            if obj.get("type") in ("message_stop", "result"):
                break

        proc.wait()
        return fullResponse, seq, False

    def _handleLlamaWithSse(self, sessionId, content, assistantMsgId, conn, stream):
        conn2 = sqlite3.connect(CHAT_DB_PATH)
        conn2.row_factory = sqlite3.Row
        priorMessages = conn2.execute("SELECT id, role, content, createdAt FROM messages WHERE sessionId=? ORDER BY createdAt ASC", (sessionId,)).fetchall()
        conn2.close()

        messages = []
        for msg in priorMessages:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": content})

        try:
            resp = requests.post(
                "http://localhost:8080/v1/chat/completions",
                json={"model": "local", "messages": messages, "stream": True},
                stream=True,
                timeout=600,
            )
            resp.raise_for_status()
        except Exception as e:
            return "", 0, False

        fullResponse = ""
        seq = 0
        try:
            for line in resp.iter_lines():
                if stream.cancelRequested:
                    break
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                text = delta.get("content", "")
                if text:
                    fullResponse += text
                    seq += 1
                    persistMessageEvent(conn, assistantMsgId, seq, "text", {"content": text})
                    stream.lastCommittedSeq = seq
                    stream.fanout({'kind': 'committed', 'seq': seq, 'type': 'text', 'payload': {'content': text}})
                    stream.fanout({'kind': 'delta', 'blockIndex': seq, 'blockType': 'text', 'textChunk': text})
                if choices[0].get("finish_reason") is not None:
                    break
        except Exception:
            pass

        return fullResponse, seq, False

    def _notifyNtfy(self, topic):
        try:
            requests.post(f"https://ntfy.sh/{topic}", data="Response ready", timeout=5)
        except Exception:
            pass

    def handlePostPermission(self, sessionId):
        if not self._checkAuth():
            return
        body = self._readBody()
        targetUser = body.get("username", "")
        if not targetUser:
            self.jsonResp(self.handler, {"error": "username required"}, 400)
            return
        if self.userRole != "admin" and not self._getChatDb().execute("SELECT 1 FROM sessions WHERE id=? AND owner=?", (sessionId, self.user)).fetchone():
            self.jsonResp(self.handler, {"error": "forbidden"}, 403)
            return
        # Verify target user exists
        conn = sqlite3.connect(CHAT_USERS_DB_PATH)
        target = conn.execute("SELECT 1 FROM users WHERE username=?", (targetUser,)).fetchone()
        conn.close()
        if not target:
            self.jsonResp(self.handler, {"error": "user not found"}, 404)
            return
        conn2 = self._getChatDb()
        conn2.execute("UPDATE sessions SET owner=? WHERE id=?", (targetUser, sessionId))
        conn2.commit()
        conn2.close()
        self.jsonResp(self.handler, {"ok": True})

    def handlePostCancel(self, sessionId, messageId):
        if not self._checkAuth():
            return
        conn = self._getChatDb()
        sessionRow = conn.execute("SELECT owner FROM sessions WHERE id=?", (sessionId,)).fetchone()
        if not sessionRow:
            conn.close()
            self.jsonResp(self.handler, {"error": "session not found"}, 404)
            return
        if self.userRole != "admin" and sessionRow["owner"] != self.user:
            conn.close()
            self.jsonResp(self.handler, {"error": "forbidden"}, 403)
            return
        msgRow = conn.execute("SELECT id, status FROM messages WHERE id=? AND sessionId=?", (messageId, sessionId)).fetchone()
        if not msgRow:
            conn.close()
            self.jsonResp(self.handler, {"error": "not found"}, 404)
            return
        if msgRow["status"] != "streaming":
            conn.close()
            self.jsonResp(self.handler, {"error": "not streaming", "status": msgRow["status"]}, 409)
            return
        stream = getActiveStream(messageId)
        if stream is None:
            maxSeq = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM messageEvents WHERE messageId=?", (messageId,)).fetchone()[0]
            persistMessageEvent(conn, messageId, maxSeq + 1, "error", {"reason": "canceled"})
            conn.execute("UPDATE messages SET status='canceled' WHERE id=?", (messageId,))
            conn.commit()
            conn.close()
            self.jsonResp(self.handler, {"status": "canceled", "note": "no active stream — DB cleanup only"})
            return
        stream.requestCancel()
        conn.close()
        self.jsonResp(self.handler, {"status": "canceling"})

    def handlePostAuth(self):
        length = int(self.handler.headers.get("Content-Length", 0))
        raw = self.handler.rfile.read(length)
        body = json.loads(raw) if raw else {}
        username = body.get("username", "").strip()
        password = body.get("password", "")
        if not username or not password:
            self.jsonResp(self.handler, {"error": "username and password required"}, 400)
            return
        conn = sqlite3.connect(CHAT_USERS_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT password_hash, role FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if not row or not _verifyPassword(password, row["password_hash"]):
            self.jsonResp(self.handler, {"error": "invalid credentials"}, 401)
            return
        token = _generateToken(username)
        tokenExpires = int(time.time()) + 2592000
        conn2 = sqlite3.connect(CHAT_USERS_DB_PATH)
        conn2.execute("INSERT OR REPLACE INTO tokens (token, username, expiresAt) VALUES (?, ?, ?)",
                     (token, username, tokenExpires))
        conn2.commit()
        conn2.close()
        self.jsonResp(self.handler, {"token": token, "username": username, "role": row["role"], "expiresAt": tokenExpires})

    def handlePostRegister(self):
        # Only allow registration if no users exist (one-time setup)
        conn = sqlite3.connect(CHAT_USERS_DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        if count > 0:
            self.jsonResp(self.handler, {"error": "registration disabled — users already exist"}, 403)
            return
        length = int(self.handler.headers.get("Content-Length", 0))
        raw = self.handler.rfile.read(length)
        body = json.loads(raw) if raw else {}
        username = body.get("username", "").strip()
        password = body.get("password", "")
        if not username or len(password) < 4:
            self.jsonResp(self.handler, {"error": "username required and password must be >= 4 chars"}, 400)
            return
        success = _createUserIfNotExists(username, password, "admin")
        if success:
            self.jsonResp(self.handler, {"ok": True, "message": "Admin user created. Use login endpoint for future auth."})
        else:
            self.jsonResp(self.handler, {"error": "user already exists"}, 409)

    def handlePostChangePassword(self):
        if not self._checkAuth():
            return
        length = int(self.handler.headers.get("Content-Length", 0))
        raw = self.handler.rfile.read(length)
        body = json.loads(raw) if raw else {}
        oldPassword = body.get("oldPassword", "")
        newPassword = body.get("newPassword", "")
        if not oldPassword or len(newPassword) < 4:
            self.jsonResp(self.handler, {"error": "current password and new password (>= 4 chars) required"}, 400)
            return
        conn = sqlite3.connect(CHAT_USERS_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT password_hash FROM users WHERE username=?", (self.user,)).fetchone()
        conn.close()
        if not row or not _verifyPassword(oldPassword, row["password_hash"]):
            self.jsonResp(self.handler, {"error": "invalid current password"}, 401)
            return
        newHash = _hashPassword(newPassword)
        conn2 = sqlite3.connect(CHAT_USERS_DB_PATH)
        conn2.execute("UPDATE users SET password_hash=? WHERE username=?", (newHash, self.user))
        conn2.commit()
        conn2.close()
        self.jsonResp(self.handler, {"ok": True})
