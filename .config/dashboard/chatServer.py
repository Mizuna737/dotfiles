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

CHAT_CONFIG_PATH = os.path.expanduser("~/.config/dashboard/chat.conf")
CHAT_DB_PATH = os.path.expanduser("~/.config/dashboard/chat.db")

# Regex for ANSI escape sequences
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')



def loadChatConfig():
    config = configparser.ConfigParser()
    with open(CHAT_CONFIG_PATH) as f:
        config.read_string("[chat]\n" + f.read())
    return {"ntfyTopic": config["chat"].get("ntfy_topic", ""), "authToken": config["chat"].get("auth_token", "")}


CHAT_CONFIG = loadChatConfig()


def initChatDb():
    conn = sqlite3.connect(CHAT_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            title TEXT,
            createdAt INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            sessionId TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            createdAt INTEGER NOT NULL
        )
    """)
    conn.commit()
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN opcodeSessionId TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE messages ADD COLUMN events TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()


initChatDb()


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

    def _checkAuth(self):
        authHeader = self.handler.headers.get("Authorization", "")
        if not authHeader.startswith("Bearer "):
            self.jsonResp(self.handler, {"error": "unauthorized"}, 401)
            return False
        token = authHeader[7:]
        if token != CHAT_CONFIG["authToken"]:
            self.jsonResp(self.handler, {"error": "unauthorized"}, 401)
            return False
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
        rows = conn.execute("SELECT id, model, title, createdAt FROM sessions ORDER BY createdAt DESC").fetchall()
        conn.close()
        self.jsonResp(self.handler, [{"id": r["id"], "model": r["model"], "title": r["title"], "createdAt": r["createdAt"]} for r in rows])

    def handleGetHistory(self, sessionId):
        if not self._checkAuth():
            return
        conn = self._getChatDb()
        rows = conn.execute("SELECT id, role, content, createdAt, events FROM messages WHERE sessionId=? ORDER BY createdAt ASC", (sessionId,)).fetchall()
        conn.close()
        self.jsonResp(self.handler, [{"id": r["id"], "role": r["role"], "content": r["content"], "createdAt": r["createdAt"], "events": r["events"]} for r in rows])

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
        sessionId = None
        if model == "qwen":
            sessionId = str(uuid.uuid4())
        elif model == "claude":
            sessionId = str(uuid.uuid4())
        else:
            self.jsonResp(self.handler, {"error": "invalid model"}, 400)
            return
        conn = sqlite3.connect(CHAT_DB_PATH)
        conn.execute("INSERT INTO sessions (id, model, title, createdAt) VALUES (?, ?, ?, ?)", (sessionId, model, None, int(time.time())))
        conn.commit()
        conn.close()
        self.jsonResp(self.handler, {"id": sessionId, "model": model, "createdAt": int(time.time())})

    def handlePostMessage(self, sessionId):
        if not self._checkAuth():
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
        conn.execute("INSERT INTO messages (id, sessionId, role, content, createdAt) VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), sessionId, "user", content, int(time.time())))
        conn.commit()
        conn.close()

        self.handler.send_response(200)
        self.handler.send_header("Content-Type", "text/event-stream")
        self.handler.send_header("Cache-Control", "no-cache")
        self.handler.send_header("Access-Control-Allow-Origin", "*")
        self.handler.end_headers()

        fullResponse = ""
        turnEvents = []
        if model == "qwen":
            fullResponse, turnEvents = self._handleQwen(sessionId, content)
        elif model == "claude":
            fullResponse, turnEvents = self._handleClaude(sessionId, content)

        if fullResponse or turnEvents:
            conn3 = sqlite3.connect(CHAT_DB_PATH)
            eventsJson = json.dumps(turnEvents) if model == "qwen" and turnEvents else None
            conn3.execute("INSERT INTO messages (id, sessionId, role, content, createdAt, events) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), sessionId, "assistant", fullResponse, int(time.time()), eventsJson))
            conn3.commit()
            conn3.close()

        try:
            self.handler.wfile.write(b'data: {"type": "done"}\n\n')
            self.handler.wfile.flush()
        except OSError:
            pass

        if CHAT_CONFIG.get("ntfyTopic"):
            threading.Thread(target=self._notifyNtfy, args=(CHAT_CONFIG["ntfyTopic"],), daemon=True).start()

    def _streamWrite(self, data):
        try:
            self.handler.wfile.write(f'data: {json.dumps(data)}\n\n'.encode())
            self.handler.wfile.flush()
            return True
        except OSError:
            return False

    def _handleQwen(self, sessionId, content):
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

        return self._runQwenWithPty(cmd, sessionId)

    def _runQwenWithPty(self, cmd, sessionId):
        """Run opencode with a PTY, streaming JSON events."""
        master_fd = None
        proc = None
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

            capturedSessionId = None
            turnEvents = []
            pendingThinking = ""
            pendingText = ""
            buffer = ""
            conn2 = sqlite3.connect(CHAT_DB_PATH)
            conn2.row_factory = sqlite3.Row
            procTimeout = 600  # 10-minute total timeout for the whole process
            startTime = time.time()
            idleSince = time.time()

            while True:
                elapsed = time.time() - startTime
                if elapsed > procTimeout:
                    # Hard timeout — kill the process
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    break

                # Check if process has exited
                poll = proc.poll()
                if poll is not None and poll != 0:
                    # Process exited with error — buffer already has stderr via PTY
                    break

                if poll is not None:
                    # Process exited cleanly — drain remaining buffer
                    break

                # Select on PTY master with timeout
                rlist, _, xlist = select.select([master_fd], [], [master_fd], 5.0)

                if xlist:
                    # Error on PTY — process likely died
                    break

                if rlist:
                    try:
                        data = os.read(master_fd, 8192)
                    except OSError:
                        break

                    if not data:
                        # EOF on PTY master — process exited
                        break

                    text = data.decode('utf-8', errors='replace')
                    buffer += str(text)

                    # Process buffer line by line
                    lines = buffer.split('\n')
                    buffer = lines[-1]  # Keep incomplete last line in buffer

                    for line in lines[:-1]:
                        cleanLine = _stripAnsi(line).strip()
                        if not cleanLine:
                            continue

                        # Try to parse as JSON event
                        event = None
                        try:
                            event = json.loads(cleanLine)
                        except json.JSONDecodeError:
                            pass

                        # Process JSON events
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
                                    turnEvents.append({"type": "thinking", "content": pendingThinking})
                                    pendingThinking = ""
                                pendingText += textContent
                                if not self._streamWrite({"type": "token", "content": textContent}):
                                    proc.kill()
                                    return pendingText, turnEvents

                        elif eType == "reasoning":
                            textContent = part.get("text", "")
                            if textContent:
                                if pendingText:
                                    turnEvents.append({"type": "text", "content": pendingText})
                                    pendingText = ""
                                pendingThinking += textContent
                                if not self._streamWrite({"type": "thinking", "content": textContent}):
                                    proc.kill()
                                    return "", turnEvents

                        elif eType == "tool_use":
                            state = part.get("state", {})
                            if state.get("status") == "completed":
                                if pendingThinking:
                                    turnEvents.append({"type": "thinking", "content": pendingThinking})
                                    pendingThinking = ""
                                if pendingText:
                                    turnEvents.append({"type": "text", "content": pendingText})
                                    pendingText = ""
                                toolEvt = {
                                    "type": "tool",
                                    "tool": part.get("tool", ""),
                                    "input": state.get("input", {}),
                                    "output": state.get("output", ""),
                                }
                                turnEvents.append(toolEvt)
                                if not self._streamWrite(toolEvt):
                                    proc.kill()
                                    return "", turnEvents

                    idleSince = time.time()

                # If we've been idle for 60 seconds, check if process is still responsive
                if time.time() - idleSince > 60:
                    if proc.poll() is not None:
                        break

            if pendingThinking:
                turnEvents.append({"type": "thinking", "content": pendingThinking})
            if pendingText:
                turnEvents.append({"type": "text", "content": pendingText})

            proc.wait()
            conn2.close()
            return pendingText, turnEvents

        finally:
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            # Ensure process is cleaned up
            try:
                if proc is not None and proc.poll() is None:
                    proc.kill()
                    proc.wait()
            except Exception:
                pass

    def _handleClaude(self, sessionId, content):
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
        turnEvents = []

        for line in proc.stdout:  # type: ignore[union-attr]
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
            elif obj.get("type") == "content_block_delta":
                try:
                    text = obj["delta"]["text"]
                except (KeyError, TypeError):
                    pass
            if text:
                if not self._streamWrite({"type": "token", "content": text}):
                    return "", turnEvents
            if obj.get("type") in ("message_stop", "result"):
                break

        proc.wait()
        return "", turnEvents

    def _notifyNtfy(self, topic):
        try:
            requests.post(f"https://ntfy.sh/{topic}", data="Response ready", timeout=5)
        except Exception:
            pass
