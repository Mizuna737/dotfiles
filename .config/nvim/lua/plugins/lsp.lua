return {
	{
		-- The main LSP plugin
		"neovim/nvim-lspconfig",
		-- If you prefer, you can also do this in the LazyVim config = {} block
		opts = {
			-- Ensure your language servers are listed here if you want them auto-installed
			servers = {
				lua_ls = {
					settings = {
						Lua = {
							diagnostics = {
								-- Add AwesomeWM's global variables here:
								globals = { "vim", "client", "awesome", "root", "screen" },
								disable = { "lowercase-global" },
							},
						},
					},
				},
			},
		},
	},
}
