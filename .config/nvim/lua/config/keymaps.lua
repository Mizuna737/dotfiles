-- ~/.config/nvim/lua/config/keymaps.lua

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

map("n", "<leader>e", function()
	require("neo-tree.command").execute({
		toggle = true,
		dir = find_project_root(),
	})
end, { desc = "Explorer: Neo-Tree (project root)" })
