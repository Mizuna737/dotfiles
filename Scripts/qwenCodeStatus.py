#!/usr/bin/env python3
"""qwenCodeStatus.py — Query opencode session status from the SQLite DB."""

import sys
import json
import sqlite3
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = str(Path.home() / ".local" / "share" / "opencode" / "opencode.db")


def unescapeText(rawText):
    """Try to json-decode a text field; fall back to raw value."""
    if not rawText:
        return rawText
    try:
        return json.loads(rawText)
    except (json.JSONDecodeError, TypeError):
        return rawText


def getSessionStatus(session_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Verify session exists
    cur.execute("SELECT id FROM session WHERE id = ?", (session_id,))
    if not cur.fetchone():
        conn.close()
        print(f"error: session not found: {session_id}", file=sys.stderr)
        sys.exit(1)

    # Count tool calls
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM part p "
        "JOIN message m ON p.message_id = m.id "
        "WHERE m.session_id = ? AND json_extract(p.data, '$.type') = 'tool'",
        (session_id,),
    )
    toolCallCount = cur.fetchone()["cnt"]

    # Last tool name
    cur.execute(
        "SELECT json_extract(p.data, '$.tool') AS tool_name FROM part p "
        "JOIN message m ON p.message_id = m.id "
        "WHERE m.session_id = ? AND json_extract(p.data, '$.type') = 'tool' "
        "ORDER BY p.time_created DESC LIMIT 1",
        (session_id,),
    )
    row = cur.fetchone()
    lastTool = row["tool_name"] if row else None

    # Last activity timestamp (most recent message)
    cur.execute(
        "SELECT MAX(time_created) AS last_ts FROM message WHERE session_id = ?",
        (session_id,),
    )
    lastTsMs = cur.fetchone()["last_ts"]

    # Last assistant text snippet
    cur.execute(
        "SELECT json_extract(p.data, '$.text') AS text_content FROM part p "
        "JOIN message m ON p.message_id = m.id "
        "WHERE m.session_id = ? AND json_extract(m.data, '$.role') = 'assistant' "
        "  AND json_extract(p.data, '$.type') = 'text' "
        "ORDER BY p.time_created DESC LIMIT 1",
        (session_id,),
    )
    row = cur.fetchone()
    lastAssistantSnippet = None
    if row and row["text_content"]:
        lastAssistantSnippet = unescapeText(row["text_content"])[-200:]

    # Check for assistant messages (for stuck detection)
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM message "
        "WHERE session_id = ? AND json_extract(data, '$.role') = 'assistant'",
        (session_id,),
    )
    hasAssistant = cur.fetchone()["cnt"] > 0
    conn.close()

    # Derived fields
    nowMs = int(time.time() * 1000)
    secondsSince = int((nowMs - lastTsMs) / 1000) if lastTsMs else 0
    lastActivityIso = datetime.fromtimestamp(
        lastTsMs / 1000, tz=timezone.utc
    ).isoformat() if lastTsMs else None
    stuck = secondsSince > 240 and hasAssistant

    return {
        "sessionId": session_id,
        "toolCallCount": toolCallCount,
        "lastTool": lastTool,
        "lastActivityIso": lastActivityIso,
        "secondsSinceLastActivity": secondsSince,
        "lastAssistantSnippet": lastAssistantSnippet,
        "stuck": stuck,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Query opencode session status from SQLite DB"
    )
    parser.add_argument(
        "sessionId", help="Session id to look up"
    )
    args = parser.parse_args()

    result = getSessionStatus(args.sessionId)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
