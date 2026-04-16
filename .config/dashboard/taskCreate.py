#!/usr/bin/env python3
"""
taskCreate — append a task to today's daily note under ## Inbox.

Importable:
    from taskCreate import createTask
    createTask("Buy milk", due="friday", priority="🔼", domain="#personal")

CLI:
    createtask <text> [due] [priority] [domain] [desc]
    createtask "Buy milk" friday "🔼" "#personal" ""
"""
import sys
import os
import subprocess
from datetime import date, timedelta

VAULT = os.path.expanduser("~/Documents/The Vault")
TEMPLATE = os.path.join(VAULT, "Templates/Daily Notes Template.md")
DAILY_NOTES = os.path.join(VAULT, "Daily Notes")
PARSEDATE = os.path.expanduser("~/Scripts/parsedate")


def resolveDueDate(due):
    if not due or due in ("", "skip"):
        return ""
    try:
        return subprocess.check_output([PARSEDATE, due], text=True).strip()
    except subprocess.CalledProcessError:
        return ""


def createTask(text, due=None, priority=None, domain=None, desc=None):
    """Write a task line to today's daily note. Returns the written line."""
    today = date.today()
    todayStr = today.strftime("%Y-%m-%d")
    notePath = os.path.join(DAILY_NOTES, f"{todayStr}.md")

    parsedDate = resolveDueDate(due) if due else ""

    parts = [f"- [ ] {text}"]
    if priority and priority not in ("", "skip"):
        parts.append(priority)
    if domain and domain not in ("", "skip"):
        parts.append(domain)
    if desc and desc.strip():
        parts.append(f"[desc:: {desc.strip()}]")
    if parsedDate:
        parts.append(f"[[{parsedDate}]]")
    taskLine = " ".join(parts)

    if os.path.exists(notePath):
        with open(notePath, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        day = today.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        friendlyDate = today.strftime(f"%A, %B {day}{suffix} %Y")
        if os.path.exists(TEMPLATE):
            with open(TEMPLATE, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace('<% tp.date.now("YYYY-MM-DD") %>', todayStr)
            content = content.replace('<% tp.date.yesterday("YYYY-MM-DD") %>', yesterday)
            content = content.replace('<% tp.date.tomorrow("YYYY-MM-DD") %>', tomorrow)
            content = content.replace('<% tp.date.now("dddd, MMMM Do YYYY") %>', friendlyDate)
        else:
            content = f"---\ndate: {todayStr}\ntags: [daily]\n---\n\n# {friendlyDate}\n\n## Inbox\n\n## Tasks\n"

    lines = content.split("\n")
    inboxIdx = next((i for i, l in enumerate(lines) if l.strip() == "## Inbox"), None)
    if inboxIdx is not None:
        insertIdx = inboxIdx + 1
        while insertIdx < len(lines) and (
            lines[insertIdx].strip() == ""
            or lines[insertIdx].strip().startswith("<!--")
            or lines[insertIdx].strip().startswith("<--")
        ):
            insertIdx += 1
    else:
        insertIdx = len(lines)

    lines.insert(insertIdx, taskLine)
    with open(notePath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return taskLine


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: createtask <text> [due] [priority] [domain] [desc]", file=sys.stderr)
        sys.exit(1)
    args = sys.argv[1:]
    taskText = args[0]
    taskDue      = args[1] if len(args) > 1 else None
    taskPriority = args[2] if len(args) > 2 else None
    taskDomain   = args[3] if len(args) > 3 else None
    taskDesc     = args[4] if len(args) > 4 else None
    line = createTask(taskText, taskDue, taskPriority, taskDomain, taskDesc)
    print(line)
