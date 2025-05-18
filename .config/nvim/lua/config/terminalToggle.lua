local terminalBufnr = nil

function toggleTerminal()
	local currentWin = vim.api.nvim_get_current_win()
	local terminalWin = nil
	local isBottomWin = false

	-- Check if terminal buffer exists and is valid
	if terminalBufnr and vim.api.nvim_buf_is_valid(terminalBufnr) then
		for _, win in ipairs(vim.api.nvim_list_wins()) do
			if vim.api.nvim_win_get_buf(win) == terminalBufnr then
				terminalWin = win
				break
			end
		end
	end

	if terminalWin then
		-- Check if terminal is in the bottom-most window
		local winInfo = vim.fn.getwininfo(terminalWin)[1]
		local screenHeight = vim.o.lines - vim.o.cmdheight
		isBottomWin = (winInfo.winrow + winInfo.height - 1 >= screenHeight)

		if terminalWin == currentWin then
			-- Already in the terminal: toggle it off
			vim.cmd("stopinsert")
			pcall(vim.api.nvim_win_close, terminalWin, true)
		elseif isBottomWin then
			-- Terminal is already at the bottom: just switch to it and insert
			vim.api.nvim_set_current_win(terminalWin)
			vim.cmd("startinsert")
		else
			-- Move terminal to bottom and resize
			vim.api.nvim_set_current_win(terminalWin)
			vim.cmd("botright split")
			vim.cmd("resize 30")
			vim.api.nvim_win_set_buf(0, terminalBufnr)

			if terminalWin ~= vim.api.nvim_get_current_win() then
				pcall(vim.api.nvim_win_close, terminalWin, true)
			end
			vim.cmd("startinsert")
		end
	elseif terminalBufnr and vim.api.nvim_buf_is_valid(terminalBufnr) then
		-- Terminal buffer exists but isn't shown: show it
		vim.cmd("botright split")
		vim.cmd("resize 30")
		vim.api.nvim_win_set_buf(0, terminalBufnr)
		vim.cmd("startinsert")
	else
		-- Create new terminal
		vim.cmd("botright split")
		vim.cmd("resize 30")
		vim.cmd("terminal")
		terminalBufnr = vim.api.nvim_get_current_buf()
		vim.cmd("startinsert")
	end
end

vim.api.nvim_create_user_command("ToggleTerminal", toggleTerminal, {})
vim.keymap.set("n", "<leader>t", ":ToggleTerminal<CR>", { desc = "Toggle terminal in bottom split" })
vim.keymap.set("t", "<Esc>", [[<C-\><C-n>]], { noremap = true, silent = true, desc = "Exit terminal mode" })
