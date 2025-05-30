-- ~/.config/nvim/lua/config/lazy.lua

-- Path to lazy.nvim
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"

-- Clone lazy.nvim if not already present
if not vim.loop.fs_stat(lazypath) then
	vim.fn.system({
		"git",
		"clone",
		"--filter=blob:none",
		"https://github.com/folke/lazy.nvim.git",
		"--branch=stable", -- latest stable release
		lazypath,
	})
end
vim.opt.rtp:prepend(lazypath)

-- Setup
require("lazy").setup({
	-- 1) LazyVim itself:
	{
		"folke/LazyVim",
		import = "lazyvim.plugins",
	},
	-- 2) Optionally import extra LazyVim “modules” if you'd like:
	-- { import = "lazyvim.plugins.extras.linting.eslint" },
	-- { import = "lazyvim.plugins.extras.formatting.prettier" },
	-- { import = "lazyvim.plugins.extras.lang.typescript" },

	-- 3) Add your own plugins here:
	{ import = "plugins" },
}, {
	defaults = {
		-- Your plugin specs can go in separate files in `lua/plugins`
		lazy = false,
		version = false,
	},
	install = { colorscheme = { "habamax" } },
	checker = { enabled = true }, -- automatically check for plugin updates
	performance = {
		rtp = {
			disabled_plugins = {
				"netrwPlugin",
				-- and others you don’t need...
			},
		},
	},
})

local pywal = require("pywal")
pywal.setup()
