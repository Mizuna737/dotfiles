--------------------------------
-- defaultApps.lua
-- Central file defining default applications
--------------------------------

local defaultApps = {
	terminalCommand = "alacritty -e tmux new-session -A -s main",
	terminal = "alacritty",
	browserCommand = "qutebrowser",
	browser = "qutebrowser",
	editor = "NeoVim",
	-- somewhere near your other commands…
	editorCommand = [[
  alacritty --class NeoVim -e \
    tmux new-session -A -s code -n NeoVim nvim 
]],
	fileManagerCommand = [[
  alacritty --class Ranger -e \
    tmux new-session -A -s files -n Ranger ranger
]],
	fileManager = "Ranger",
	neovim = [[
  alacritty --class NeoVim -e \
    tmux new-session -A -s code -n NeoVim nvim
]],

	alacritty = "alacritty -e tmux new-session -A -s main",
}

return defaultApps
