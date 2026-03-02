return {
	"nvim-neo-tree/neo-tree.nvim",
	opts = function(_, opts)
		opts.filesystem = opts.filesystem or {}
		opts.filesystem.hijack_netrw_behavior = "disabled"
	end,
}
