return {
	"folke/snacks.nvim",
	opts = {
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
