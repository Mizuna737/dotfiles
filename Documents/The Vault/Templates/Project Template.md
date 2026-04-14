<%*
  if (tp.file.title === "Untitled") {
    const fileName = await tp.system.prompt("Project Title:");
    if (fileName) await tp.file.rename(fileName);
  }
-%>
---
title: <% tp.file.title %>
status: active
tags: [project]
domain: <% tp.system.suggester(["work", "personal", "technical"], ["work", "personal", "technical"]) %>
created: "[[<% tp.date.now("YYYY-MM-DD") %>]]"
---
## Goal
<-- One or two sentences. What does done look like? -->

## Tasks 
<-- Tasks related to this project -->

## Notes
<-- Running notes, decisions, context -->

## Related
<-- Links to people, meetings, reference notes -->
