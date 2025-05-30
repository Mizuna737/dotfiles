-- ~/.config/nvim/lua/config/keymapend, s.lua

local map = vim.keymap.set
local uv = vim.loop
local fs = vim.fs

local function find_project_root()
	-- start from the directory of the current buffer, or fallback to cwd
	local path = vim.fn.expand("%:p:h") ~= "" and vim.fn.expand("%:p:h") or uv.cwd()
	-- look upward for a `.git` (you can add more markers here)
	local git_dir = fs.find(".git", { upward = true, path = path })[1]
	if git_dir then
		-- fs.dirname("/foo/bar/.git") -> "/foo/bar"
		return fs.dirname(git_dir)
	end
	return uv.cwd()
end

map("n", "<leader>e", ":RnvimrToggle<CR>", { noremap = true, silent = true })

map("n", "<leader>dd", function()
	-- Save all listed buffers
	vim.cmd("wall")

	-- Get all listed buffers
	for _, bufnr in ipairs(vim.api.nvim_list_bufs()) do
		local buftype = vim.api.nvim_buf_get_option(bufnr, "buftype")
		if buftype ~= "terminal" and vim.api.nvim_buf_is_loaded(bufnr) then
			vim.api.nvim_buf_delete(bufnr, { force = true })
		end
	end

	require("snacks").dashboard()
end, { desc = "Save and close all non-terminal buffers" })

map("n", "<leader>h", function()
	require("snacks").dashboard()
end, { desc = "Home (Dashboard)" })

map("n", "<leader>ya", ":%y+<CR>", { desc = "Yank entire buffer to clipboard" })

map("n", "<leader>rp", function()
	vim.cmd("normal! G$vgg0p")
end, { desc = "Replace buffer from clipboard" })

vim.api.nvim_create_user_command("ReloadKeymaps", function()
	package.loaded["config.keymaps"] = nil
	require("config.keymaps")
end, {})

vim.api.nvim_create_autocmd("FocusGained", {
	callback = function()
		vim.cmd("colorscheme pywal")
	end,
})
