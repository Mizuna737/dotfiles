-- Minimal config for Quick Notes nvim instance

-- Focuses the last line of the buffer and enters insert mode ready for new notes.
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

-- Extracts today's ## Notes into the active file, updates pointers, and reloads
-- the buffer. inotifywait keeps watching /tmp/ so no watcher restart is needed.
local function refreshDailyNoteBuffer()
	local today = os.date("%Y-%m-%d")
	local vault = os.getenv("HOME") .. "/Documents/The Vault"
	local dailyNote = vault .. "/Daily Notes/" .. today .. ".md"
	local activeFile = "/tmp/quicknotes-" .. today .. ".md"

	vim.cmd("silent! write")

	local f = io.open(dailyNote, "r")
	if not f then
		vim.notify("Could not open daily note: " .. dailyNote)
		return
	end
	local lines = {}
	for line in f:lines() do table.insert(lines, line) end
	f:close()

	local startIdx = nil
	for i, line in ipairs(lines) do
		if line:match("^## Notes%s*$") then startIdx = i break end
	end

	local content = {}
	if startIdx then
		local endIdx = #lines + 1
		for i = startIdx + 1, #lines do
			if lines[i]:match("^## ") then endIdx = i break end
		end
		for i = startIdx + 1, endIdx - 1 do table.insert(content, lines[i]) end
		while #content > 0 and content[1]:match("^%s*$") do table.remove(content, 1) end
		while #content > 0 and content[#content]:match("^%s*$") do table.remove(content) end
	end

	local out = io.open(activeFile, "w")
	if not out then vim.notify("Could not write active file") return end
	for _, line in ipairs(content) do out:write(line .. "\n") end
	out:close()

	local aptr = io.open("/tmp/quicknotes-active.ptr", "w")
	if aptr then aptr:write(activeFile) aptr:close() end
	local dptr = io.open("/tmp/quicknotes-dailynote.ptr", "w")
	if dptr then dptr:write(dailyNote) dptr:close() end

	local currentPath = vim.api.nvim_buf_get_name(vim.api.nvim_get_current_buf())
	if currentPath ~= activeFile then
		local oldBuf = vim.api.nvim_get_current_buf()
		vim.cmd("edit " .. vim.fn.fnameescape(activeFile))
		if vim.api.nvim_buf_is_valid(oldBuf) then
			vim.api.nvim_buf_delete(oldBuf, { force = true })
		end
	else
		vim.cmd("edit!")
	end

	vim.fn.setenv("QUICKNOTES_DATE", today)
end

-- Checks if the buffer is stale and prompts the user to refresh if so.
-- Deferred via vim.schedule to avoid conflicting with focusEnd's insert mode.
local function checkStaleBuffer()
	vim.schedule(function()
		local noteDate = os.getenv("QUICKNOTES_DATE") or "unknown"
		local today = os.date("%Y-%m-%d")
		if noteDate == today then return end

		vim.cmd("stopinsert")
		local choice = vim.fn.confirm(
			"Quick Notes is from " .. noteDate .. ". Switch to today?",
			"&Yes\n&No"
		)
		if choice == 1 then
			refreshDailyNoteBuffer()
		end
	end)
end

local function onEnterDo()
	focusEnd()
	checkStaleBuffer()
end

vim.api.nvim_create_user_command("RefreshDailyNoteBuffer", refreshDailyNoteBuffer, {})

-- Write buffer to disk on focus loss so the shell watcher can pick it up
local function saveOnFocusLost()
	vim.cmd("silent! write")
end

vim.api.nvim_create_autocmd({ "VimEnter", "FocusGained", "BufEnter" }, {
	callback = onEnterDo,
})

vim.api.nvim_create_autocmd("FocusLost", {
	callback = saveOnFocusLost,
})

vim.opt.wrap = true
vim.opt.linebreak = true
vim.opt.spell = true
vim.opt.swapfile = false
vim.opt.undofile = true
vim.bo.filetype = "markdown"
