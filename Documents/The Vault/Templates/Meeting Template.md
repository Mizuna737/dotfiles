<%*
  if (tp.file.title === "Untitled") {
    const fileName = await tp.system.prompt("Meeting Title:");
    if (fileName) await tp.file.rename(fileName);
  }
  tp.hooks.on_all_templates_executed(async () => {
    const file = app.vault.getAbstractFileByPath(tp.file.path(true));
    if (file) {
      const content = await app.vault.read(file);
      await app.vault.modify(file, content);
    }
  });
-%>
---
date: <%*
  const dateInput = await tp.system.prompt("Date (e.g. 'today', 'friday', or YYYY-MM-DD):", tp.date.now("YYYY-MM-DD"));
  const parseDate = (input) => {
    const s = input.toLowerCase().trim();
    if (s === "today") return new Date();
    if (s === "tomorrow") { const d = new Date(); d.setDate(d.getDate() + 1); return d; }
    if (s === "next week") { const d = new Date(); d.setDate(d.getDate() + 7); return d; }
    const days = ["sunday","monday","tuesday","wednesday","thursday","friday","saturday"];
    const dayIndex = days.indexOf(s);
    if (dayIndex !== -1) {
      const d = new Date();
      const diff = (dayIndex - d.getDay() + 7) % 7 || 7;
      d.setDate(d.getDate() + diff);
      return d;
    }
    // Parse YYYY-MM-DD as local time by splitting manually
    const parts = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (parts) {
      return new Date(parseInt(parts[1]), parseInt(parts[2]) - 1, parseInt(parts[3]));
    }
    const direct = new Date(input);
    return isNaN(direct) ? new Date() : direct;
  };
  const parsed = parseDate(dateInput);
  const yyyy = parsed.getFullYear();
  const mm = String(parsed.getMonth() + 1).padStart(2, "0");
  const dd = String(parsed.getDate()).padStart(2, "0");
  const dateStr = `${yyyy}-${mm}-${dd}`;
  tR += `"[[${dateStr}]]"`;
%>
start: "<%* tR += await tp.system.prompt("Start time (HH:MM, 24h):", "09:00"); %>"
end: "<%* tR += await tp.system.prompt("End time (HH:MM, 24h):", "09:30"); %>"
type: <%*
  const type = await tp.system.suggester(
    ["1on1", "team", "stakeholder", "external", "ad-hoc"],
    ["1on1", "team", "stakeholder", "external", "ad-hoc"],
    false
  );
  tR += type ?? "";
%>
attendees: [<%*
  const peopleFiles = app.vault.getFiles().filter(f => f.path.startsWith("People/"));
  const peopleNames = peopleFiles.map(f => f.basename);
  const selected = [];
  while (true) {
    const remaining = peopleNames.filter(n => !selected.includes(n));
    const displayOptions = [
      "── Done ──",
      "👤 + New Person",
      ...remaining,
    ];
    const valueOptions = [
      null,
      "__new__",
      ...remaining,
    ];
    const pick = await tp.system.suggester(
      displayOptions,
      valueOptions,
      false,
      `Attendees (${selected.length} selected) — pick or Done`
    );
    if (!pick) break;
    if (pick === "__new__") {
      const newName = await tp.system.prompt("New person's name:");
      if (newName) {
        const templateFile = app.vault.getAbstractFileByPath("Templates/People Template.md");
        if (templateFile) {
          await tp.file.create_new(
            templateFile,
            newName,
            false,
            app.vault.getAbstractFileByPath("People")
          );
          peopleNames.push(newName);
          selected.push(newName);
        } else {
          new Notice("Could not find People Template at Templates/People Template.md");
        }
      }
    } else {
      selected.push(pick);
    }
  }
  tR += selected.map(n => `"[[${n}]]"`).join(", ");
%>]
tags: [meeting]
created: <% tp.date.now("YYYY-MM-DD") %>
---

## Attendees
```dataview
LIST WITHOUT ID attendee
FROM "Meetings"
WHERE file.path = this.file.path
FLATTEN attendees AS attendee
```

## Agenda

## Notes

## Tasks

## Follow-ups