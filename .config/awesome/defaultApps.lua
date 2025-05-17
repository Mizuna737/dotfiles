--------------------------------
-- defaultApps.lua
-- Central file defining default applications
--------------------------------

local defaultApps = {
	terminalCommand = "alacritty",
	terminal = "alacritty",
	browserCommand = "qutebrowser",
	browser = "qutebrowser",
	editor = "NeoVim",
	editorCommand = "alacritty --class NeoVim -e nvim",
	kitty = "kitty nvim",
	fileManagerCommand = "QT_QPA_PLATFORMTHEME=qt5ct QT_STYLE_OVERRIDE=kvantum dolphin",
	fileManager = "dolphin",
}

return defaultApps
