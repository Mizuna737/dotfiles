return {
	"nvim-neo-tree/neo-tree.nvim",
	opts = {
		filesystem = {
			filtered_items = {
				hide_dotfiles = false,
				hide_hidden = false,
				visible = true,
			},
		},
	},
	-- after neo-tree loads, relink the dimmed groups
	config = function(_, opts)
		require("neo-tree").setup(opts)
		vim.api.nvim_set_hl(0, "NeoTreeDimText", { link = "NeoTreeFileName" })
		vim.api.nvim_set_hl(0, "NeoTreeDotfile", { link = "NeoTreeFileName" })
	end,
}
