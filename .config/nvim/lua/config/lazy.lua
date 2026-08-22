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

-- Colours come from rubix, derived from the current wallpaper and solved to
-- stay readable through window transparency. Regenerated on every wallpaper
-- change; see ~/.config/rubix/theme.toml.
local rubixThemeDir = vim.fn.expand("~/.cache/rubix")
local rubixTheme = rubixThemeDir .. "/nvim-theme.lua"

local function applyRubixTheme()
	if vim.fn.filereadable(rubixTheme) == 1 then
		pcall(dofile, rubixTheme)
	end
end

applyRubixTheme()

-- Re-apply once plugins have finished loading. Plugins that theme themselves --
-- lualine reads the colorscheme and picks its own palette -- set up after this
-- file runs, so a single early application is overwritten by whatever they
-- chose. VeryLazy fires after startup; VimEnter is the fallback for configs
-- that never emit it.
vim.api.nvim_create_autocmd("User", {
	pattern = "VeryLazy",
	callback = applyRubixTheme,
})
vim.api.nvim_create_autocmd("VimEnter", {
	callback = function()
		vim.schedule(applyRubixTheme)
	end,
})

-- Watch the DIRECTORY, not the file. The theme is written atomically -- new
-- file, then rename -- so a watch on the path is left holding the old inode
-- and never fires again after the first swap. Watching the directory survives
-- that, because the directory entry is what changes.
local rubixWatcher = (vim.uv or vim.loop).new_fs_event()
if rubixWatcher then
	rubixWatcher:start(rubixThemeDir, {}, function(_, filename)
		if filename and filename:match("^nvim%-theme") then
			vim.schedule(applyRubixTheme)
		end
	end)
end
