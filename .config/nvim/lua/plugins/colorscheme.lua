-- ~/.config/nvim/lua/plugins/colorscheme.lua
return {
	{
		"Shatur/neovim-ayu",
		lazy = false, -- load immediately
		priority = 1000, -- load this before other plugins
		config = function()
			require("ayu").setup({
				mirage = true, -- enable mirage background
			})
			vim.cmd("colorscheme ayu")
		end,
	},
}
