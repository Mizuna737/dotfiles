#!/bin/bash

# Step 1: Show clipboard history in Rofi with null delimiters, escaping newlines
selected=$(copyq eval -- "for (i = 0; i < size(); ++i) print(i + '\t' + str(read(i)).replace('\n', '⏎') + '\0')" |
  rofi -dmenu -i -sep '\0' -0 -p "Clipboard")

# Exit if no selection made
[ -z "$selected" ] && exit 1

# Step 2: Extract index and retrieve the raw entry
index="${selected%%$'\t'*}"
entry=$(copyq read "$index")

# Step 3: Set the clipboard to the selected entry
copyq copy "$entry"

# Step 4: Simulate Ctrl+Shift+V to paste as one block (terminal-safe)
xdotool key --clearmodifiers ctrl+shift+v
