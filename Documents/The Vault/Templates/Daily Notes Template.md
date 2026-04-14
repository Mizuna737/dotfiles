---
date: <% tp.date.now("YYYY-MM-DD") %>
tags:
  - daily
yesterday: '[[<% tp.date.yesterday("YYYY-MM-DD") %>]]'
tomorrow: '[[<% tp.date.tomorrow("YYYY-MM-DD") %>]]'
---

# <% tp.date.now("dddd, MMMM Do YYYY") %>

## Unfiled Tasks
```dataviewjs
const tasks = dv.pages('"Daily Notes" OR "Meetings"')
  .file.tasks
  .where(t => !t.completed && t.position.start.col === 0);

if (tasks.length === 0) {
  dv.paragraph("_No unfiled tasks._");
} else {
  dv.taskList(tasks, true);
}
```
## Meetings
```dataview
TABLE WITHOUT ID choice(start AND end, start + "–" + end, default(start, "—")) AS Time, file.link AS Meeting, attendees AS Attendees
FROM "Meetings"
WHERE dateformat(date(date), "yyyy-MM-dd") = this.file.name
SORT start ASC
```
## Inbox
<-- Capture tasks and notes here freely -->

## Notes
<-- Anything else — observations, thoughts, context -->