-- ~/.config/nvim/init.lua
-- Disable netrw before Lazy loads
vim.g.loaded_netrw = 1
vim.g.loaded_netrwPlugin = 1
-- Load our LazyVim config (the lazy.lua file we'll create)
require("config.lazy")
require("config.terminalToggle")
require("config.keymaps")
