return {
	"folke/snacks.nvim",
	opts = {
		-- explorer picker settings
		explorer = {
			-- show all hidden files (dot-files)
			hidden = true,
			-- other Explorer options you might like:
			-- auto_close = true,
			-- watch      = false,
			-- diagnostics = false,
			-- git_status = false,
		},

		-- if you also use the files picker, show hidden there too
		picker = {
			sources = {
				files = {
					hidden = true,
					ignored = true,
				},
			},
		},
	},
}
