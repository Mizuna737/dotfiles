--------------------------------
-- defaultApps.lua
-- Central file defining default applications
--------------------------------

local defaultApps = {
	terminalCommand = "kitty --override confirm_os_window_close=0 -e tmux new-session -A -s kitty",
	terminal = "kitty",
	browserCommand = "qutebrowser",
	browser = "qutebrowser",
	editor = "neovim",
	-- somewhere near your other commands…
	editorCommand = [[
  kitty --class neovim --override confirm_os_window_close=0 -e \
    tmux new-session -A -s code -n NeoVim nvim 
]],
	fileManagerCommand = [[
  kitty --class yazi --override confirm_os_window_close=0 -e \
    tmux new-session -A -s files -n Yazi yazi
]],
	fileManager = "yazi",
	neovim = [[
  kitty --class neovim --override confirm_os_window_close=0 -e \
    tmux new-session -A -s code -n NeoVim nvim
]],
	kitty = "kitty --override confirm_os_window_close=0 -e tmux new-session -A -s kitty",
	zen = 'zen-browser --style "$HOME/.config/zen/pywal.css"',
}

return defaultApps
