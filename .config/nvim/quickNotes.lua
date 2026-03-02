-- Minimal config for Quick Notes nvim instance

local function focus_end()
	local last = vim.fn.line("$")
	local lastline = vim.fn.getline(last)

	vim.cmd("normal! G")
	if lastline ~= "" then
		vim.cmd("normal! o")
	else
		vim.cmd("startinsert!")
	end
end

vim.api.nvim_create_autocmd({ "VimEnter", "FocusGained", "BufEnter" }, {
	callback = focus_end,
})
vim.opt.wrap = true
vim.opt.linebreak = true
vim.opt.spell = true
vim.opt.swapfile = false
vim.opt.undofile = true
vim.bo.filetype = "markdown"
