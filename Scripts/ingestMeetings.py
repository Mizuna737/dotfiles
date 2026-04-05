#!/usr/bin/env python3
"""ingestMeetings.py — Parse a calendar PDF and interactively create Obsidian meeting notes."""

import sys
import os
import re
import json
import subprocess
import requests
from datetime import datetime

VAULT = "/home/max/Documents/The Vault"
MEETINGS_DIR = os.path.join(VAULT, "Meetings")
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:14b"
TODAY = datetime.now().strftime("%Y-%m-%d")

SKIP_EXACT = {
    "busy", "ooo", "deep work", "meetings", "tentative",
    "update cost allocation", "check attendance for direct reports",
}
SKIP_PREFIXES = (
    "canceled:", "cancelled:", "following:", "cs/ts shadowing",
)

BOILERPLATE_PREFIXES = (
    "join:", "meeting id:", "passcode:", "need help?", "system reference",
    "dial in by phone", "phone conference", "find a local number",
    "for organizers:", "or call in", "click here to join", "download teams",
    "join on your computer", "join the meeting now", "microsoft teams",
    "need help", "reset dial-in pin", "meeting options", "learn more",
    "for better viewing", "meeting forwarding", "one tap mobile",
    "________________",
)

TIME_RE = re.compile(
    r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\d{1,2}/\d{1,2}/\d{4})\s+'
    r'(\d{1,2}:\d{2}\s*[AP]M)\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)',
    re.IGNORECASE
)
ALL_DAY_RE = re.compile(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{1,2}/\d{1,2}/\d{4}\s+\(All day\)', re.IGNORECASE)
DAY_HEADER_RE = re.compile(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+ \d+, \d{4}')
PHONE_RE = re.compile(r'^\+?[\d\s\(\)\-,#\.]+$')
MEETING_ID_RE = re.compile(r'^\d{3}\s\d{3}\s\d{3}')
URL_RE = re.compile(r'https?://')


def shouldSkip(title):
    t = title.lower().strip()
    if t in SKIP_EXACT:
        return True
    for prefix in SKIP_PREFIXES:
        if t.startswith(prefix):
            return True
    return False


def isBoilerplate(line):
    l = line.lower().strip()
    if not l:
        return False
    for prefix in BOILERPLATE_PREFIXES:
        if l.startswith(prefix):
            return True
    if PHONE_RE.match(l):
        return True
    if MEETING_ID_RE.match(l):
        return True
    if URL_RE.search(l):
        return True
    return False


def to24h(t):
    t = re.sub(r'\s+', ' ', t.strip())
    return datetime.strptime(t, "%I:%M %p").strftime("%H:%M")


def extractNames(attendeeStr):
    # Match "Firstname [Middle] Lastname <email>" — greedy enough for compound names
    return re.findall(r'([A-Z][a-záéíóúñ\-]+(?:\s+[A-Z][a-záéíóúñ\-]+)+)\s*<', attendeeStr)


def parsePdf(path):
    result = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"pdftotext failed: {result.stderr}")
        sys.exit(1)
    return result.stdout


def extractMeetings(text):
    lines = text.splitlines()
    meetings = []

    # Index every line that starts a date/time block
    timeLineIndices = []
    for i, line in enumerate(lines):
        if TIME_RE.match(line.strip()) or ALL_DAY_RE.match(line.strip()):
            timeLineIndices.append(i)

    for pos, timeIdx in enumerate(timeLineIndices):
        timeLine = lines[timeIdx].strip()

        # Skip all-day events
        if ALL_DAY_RE.match(timeLine):
            continue

        m = TIME_RE.match(timeLine)
        if not m:
            continue

        _, dateStr, startStr, endStr = m.group(1), m.group(2), m.group(3), m.group(4)

        # Title: last non-empty line before the time line
        title = ""
        for k in range(timeIdx - 1, max(timeIdx - 4, -1), -1):
            candidate = lines[k].strip()
            if candidate and not DAY_HEADER_RE.match(candidate):
                title = candidate
                break

        if not title or shouldSkip(title):
            continue

        # Parse date/times
        dateObj = datetime.strptime(dateStr, "%m/%d/%Y")
        dateFmt = dateObj.strftime("%Y-%m-%d")
        start24 = to24h(startStr)
        end24 = to24h(endStr)

        # Collect body lines until next time line or day header
        nextBoundary = timeLineIndices[pos + 1] if pos + 1 < len(timeLineIndices) else len(lines)

        organizer = ""
        required = []
        optional = []
        bodyLines = []
        currentField = None
        fieldBuffer = ""

        def flushField():
            nonlocal currentField, fieldBuffer, organizer, required, optional
            if currentField == "organizer":
                organizer = fieldBuffer.strip()
            elif currentField == "required":
                required = extractNames(fieldBuffer)
            elif currentField == "optional":
                optional = extractNames(fieldBuffer)
            currentField = None
            fieldBuffer = ""

        for k in range(timeIdx + 1, nextBoundary):
            line = lines[k]
            stripped = line.strip()

            if not stripped:
                continue
            if DAY_HEADER_RE.match(stripped):
                break
            if isBoilerplate(stripped):
                flushField()
                continue

            if stripped.startswith("Organizer:"):
                flushField()
                currentField = "organizer"
                fieldBuffer = stripped[len("Organizer:"):].strip()
            elif stripped.startswith("Required Attendees:"):
                flushField()
                currentField = "required"
                fieldBuffer = stripped[len("Required Attendees:"):].strip()
            elif stripped.startswith("Optional Attendees:"):
                flushField()
                currentField = "optional"
                fieldBuffer = stripped[len("Optional Attendees:"):].strip()
            elif stripped.startswith("Location:"):
                flushField()
                # Don't store location, not used in notes
            elif currentField in ("required", "optional") and "<" in stripped:
                # Continuation of multi-line attendee list
                fieldBuffer += " " + stripped
            else:
                flushField()
                bodyLines.append(stripped)

        flushField()

        meetings.append({
            "title": title,
            "date": dateFmt,
            "start": start24,
            "end": end24,
            "organizer": organizer,
            "required": required,
            "optional": optional,
            "body": "\n".join(bodyLines[:15]),
        })

    return meetings


def getExistingPeople():
    peopleDir = os.path.join(VAULT, "People")
    if not os.path.exists(peopleDir):
        return set()
    return {f[:-3] for f in os.listdir(peopleDir) if f.endswith(".md")}


def createPersonNote(name):
    peopleDir = os.path.join(VAULT, "People")
    filepath = os.path.join(peopleDir, f"{name}.md")
    if os.path.exists(filepath):
        return
    content = f"""---
role:
team:
relationship:
tags: [person]
created: {TODAY}
---

## Context
<-- Who are they, what do they own, working style, what matters to them -->

## Goals & Development
<-- Their stated goals, growth areas, what you're invested in -->

## Tasks
<-- Tasks related to this person -->

## 1:1 History

## Running Notes
"""
    with open(filepath, "w") as f:
        f.write(content)


def getExistingMeetingKeys():
    """Return a set of (date, start) tuples for all notes already in MEETINGS_DIR."""
    keys = set()
    frontmatterRe = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL)
    dateRe = re.compile(r'^date:\s*"?\[?\[?(\d{4}-\d{2}-\d{2})', re.MULTILINE)
    startRe = re.compile(r'^start:\s*"?(\d{2}:\d{2})"?', re.MULTILINE)
    if not os.path.exists(MEETINGS_DIR):
        return keys
    for fname in os.listdir(MEETINGS_DIR):
        if not fname.endswith(".md"):
            continue
        try:
            with open(os.path.join(MEETINGS_DIR, fname)) as f:
                content = f.read(512)
            dateMatch = dateRe.search(content)
            startMatch = startRe.search(content)
            if dateMatch and startMatch:
                keys.add((dateMatch.group(1), startMatch.group(1)))
        except OSError:
            pass
    return keys


def generateAgenda(meeting, context, existingPeople):
    requiredNames = meeting["required"]
    optionalNames = meeting["optional"]

    systemPrompt = (
        "You are a professional meeting facilitator helping create concise Obsidian meeting note agendas. "
        "Return ONLY a markdown bullet list of agenda items. No headers, no preamble, no explanation. "
        "Each bullet should be actionable and specific."
    )

    userPrompt = f"""Meeting: {meeting['title']}
Date: {meeting['date']} at {meeting['start']}–{meeting['end']}
Organizer: {meeting['organizer'] or 'Unknown'}
Required attendees: {', '.join(requiredNames) if requiredNames else 'Unknown'}
{('Optional attendees: ' + ', '.join(optionalNames)) if optionalNames else ''}
{('Meeting description: ' + meeting['body'][:400]) if meeting['body'].strip() else ''}
User context: {context if context else 'None provided.'}

Generate the agenda bullet points now:"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": f"{systemPrompt}\n\n{userPrompt}",
            "stream": False,
            "options": {"temperature": 0.3},
        }, timeout=90)
        resp.raise_for_status()
        return resp.json()["response"].strip()
    except Exception as e:
        print(f"\n  Warning: AI request failed ({e}). Using placeholder.")
        return "- (agenda items)"


def formatAttendeeFrontmatter(names, existingPeople):
    links = [f'"[[{n}]]"' if n in existingPeople else f'"{n}"' for n in names]
    return "[" + ", ".join(links) + "]"


def sanitizeFilename(name):
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


def deriveMonth(dateStr):
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    return months[int(dateStr.split("-")[1]) - 1]


def createNote(meeting, agenda, existingPeople):
    month = deriveMonth(meeting["date"])
    filename = sanitizeFilename(f"{meeting['title']} {month}.md")
    filepath = os.path.join(MEETINGS_DIR, filename)

    if os.path.exists(filepath):
        base = filename[:-3]
        n = 2
        while os.path.exists(os.path.join(MEETINGS_DIR, f"{base} ({n}).md")):
            n += 1
        filepath = os.path.join(MEETINGS_DIR, f"{base} ({n}).md")

    # Create People notes for anyone not already in the vault
    allAttendees = meeting["required"] + [
        a for a in meeting["optional"] if a not in meeting["required"]
    ]
    for name in allAttendees:
        if name not in existingPeople:
            createPersonNote(name)
            existingPeople.add(name)
            print(f"  + Created People note: {name}")

    attendeeStr = formatAttendeeFrontmatter(allAttendees, existingPeople)

    content = f"""---
date: "[[{meeting['date']}]]"
start: "{meeting['start']}"
end: "{meeting['end']}"
type: meeting
attendees: {attendeeStr}
tags: [meeting]
created: {TODAY}
---

## Attendees
```dataviewjs
const attendees = dv.current().attendees;
if (attendees && attendees.length) {{
    dv.list(attendees);
}} else {{
    dv.paragraph("_No attendees listed._");
}}
```

## Agenda

{agenda}

## Notes

## Tasks

## Follow-ups
"""

    with open(filepath, "w") as f:
        f.write(content)

    return filepath


def main():
    if len(sys.argv) < 2:
        print("Usage: ingestMeetings.py <calendar.pdf>")
        sys.exit(1)

    pdfPath = sys.argv[1]
    if not os.path.exists(pdfPath):
        print(f"File not found: {pdfPath}")
        sys.exit(1)

    print(f"\nParsing {pdfPath}...")
    text = parsePdf(pdfPath)
    meetings = extractMeetings(text)

    if not meetings:
        print("No meetings found.")
        sys.exit(0)

    existingPeople = getExistingPeople()
    existingMeetingKeys = getExistingMeetingKeys()
    print(f"Found {len(meetings)} meetings (auto-skipped: Busy, OOO, Cancelled, All-day, etc.)\n")

    created = 0
    skipped = 0

    for idx, meeting in enumerate(meetings, 1):
        # Skip meetings that already have a note
        meetingKey = (meeting["date"], meeting["start"])
        if meetingKey in existingMeetingKeys:
            print(f"─── [{idx}/{len(meetings)}] {'─' * 48}")
            print(f"  Skipping (note exists): {meeting['title']}  {meeting['date']} {meeting['start']}\n")
            skipped += 1
            continue

        print(f"─── [{idx}/{len(meetings)}] {'─' * 48}")
        print(f"  Title:     {meeting['title']}")
        print(f"  Date:      {meeting['date']}  {meeting['start']}–{meeting['end']}")
        if meeting["organizer"]:
            print(f"  Organizer: {meeting['organizer']}")
        if meeting["required"]:
            shown = meeting["required"][:4]
            more = f"  +{len(meeting['required']) - 4} more" if len(meeting["required"]) > 4 else ""
            print(f"  Required:  {', '.join(shown)}{more}")
        print()

        try:
            answer = input("  Create note? [y/n/q to quit]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            break

        if answer == "q":
            break
        if answer != "y":
            skipped += 1
            print()
            continue

        try:
            context = input("  Agenda context (Enter to use meeting details only): ").strip()
        except (EOFError, KeyboardInterrupt):
            context = ""

        print("  Generating agenda...", end="", flush=True)
        agenda = generateAgenda(meeting, context, existingPeople)
        print(" done.")

        filepath = createNote(meeting, agenda, existingPeople)
        existingMeetingKeys.add(meetingKey)
        print(f"  ✓ Created: {os.path.basename(filepath)}\n")
        created += 1

    print(f"\nDone — {created} note(s) created, {skipped} skipped.")


if __name__ == "__main__":
    main()
