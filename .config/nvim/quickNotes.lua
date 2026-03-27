-- Minimal config for Quick Notes nvim instance

local function focusEnd()
	local last = vim.fn.line("$")
	local lastLine = vim.fn.getline(last)
	vim.cmd("normal! G")
	if lastLine ~= "" then
		vim.cmd("normal! o")
	else
		vim.cmd("startinsert!")
	end
end

-- Write buffer to disk on focus loss so the shell script can pick it up
local function saveOnFocusLost()
	vim.cmd("silent! write")
end

vim.api.nvim_create_autocmd({ "VimEnter", "FocusGained", "BufEnter" }, {
	callback = focusEnd,
})

vim.api.nvim_create_autocmd({ "FocusLost" }, {
	callback = saveOnFocusLost,
})

vim.opt.wrap = true
vim.opt.linebreak = true
vim.opt.spell = true
vim.opt.swapfile = false
vim.opt.undofile = true
vim.bo.filetype = "markdown"
