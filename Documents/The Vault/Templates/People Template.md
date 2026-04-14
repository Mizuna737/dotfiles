<%*
  if (tp.file.title === "Untitled") {
    const fileName = await tp.system.prompt("Person's Name:");
    if (fileName) await tp.file.rename(fileName);
  }
-%>
---
role: 
team: 
relationship: <% await tp.system.suggester(["direct report", "peer", "stakeholder", "external", "upline", "downline"], ["direct report", "peer", "stakeholder", "external", "upline", "downline"], false) ?? "" %>
tags: [person]
created: <% tp.date.now("YYYY-MM-DD") %>
---

## Context
<-- Who are they, what do they own, working style, what matters to them -->

## Goals & Development
<-- Their stated goals, growth areas, what you're invested in -->

## Tasks
<-- Tasks related to this person -->

## 1:1 History

## Running Notes
