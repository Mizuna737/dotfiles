--------------------------------
-- defaultApps.lua
-- Central file defining default applications
--------------------------------

local defaultApps = {
	terminalCommand = "kitty -e tmux new-session -A -s main",
	terminal = "kitty",
	browserCommand = 'zen-browser --style "$HOME/.config/zen/pywal.css"',
	browser = "zen",
	editor = "NeoVim",
	-- somewhere near your other commands…
	editorCommand = [[
  kitty --class NeoVim -e \
    tmux new-session -A -s code -n NeoVim nvim 
]],
	fileManagerCommand = [[
  kitty --class Ranger -e \
    tmux new-session -A -s files -n Ranger ranger
]],
	fileManager = "Ranger",
	neovim = [[
  kitty --class NeoVim -e \
    tmux new-session -A -s code -n NeoVim nvim
]],
	kitty = "kitty -e tmux new-session -A -s main",
	zen = 'zen-browser --style "$HOME/.config/zen/pywal.css"',
}

return defaultApps
