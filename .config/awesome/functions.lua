-- functions.lua
-- Stores all custom logic in camelCase for easy reusability.

local awful = require("awful")
local gears = require("gears")
local naughty = require("naughty")
local lain = require("lain")
local bar = require("bar")
local hotkeys_popup = require("awful.hotkeys_popup")
local wibox = require("wibox")
require("awful.hotkeys_popup.keys")
local defaultApps = require("defaultApps")

naughty.notify("functions loaded")

local M = {}

--------------------------------
-- Tag Navigation
--------------------------------

function M.viewPopulatedTag(direction)
	local screen = awful.screen.focused()
	local currentTag = screen.selected_tag
	local tags = screen.tags
	local targetTag

	if not currentTag then
		return
	end

	if direction == "next" then
		for i = (currentTag.index % #tags) + 1, #tags do
			if #tags[i]:clients() > 0 then
				targetTag = tags[i]
				break
			end
		end
		if not targetTag then
			for i = 1, currentTag.index - 1 do
				if #tags[i]:clients() > 0 then
					targetTag = tags[i]
					break
				end
			end
		end
	elseif direction == "previous" then
		for i = (currentTag.index - 2 + #tags) % #tags + 1, 1, -1 do
			if #tags[i]:clients() > 0 then
				targetTag = tags[i]
				break
			end
		end
		if not targetTag then
			for i = #tags, currentTag.index + 1, -1 do
				if #tags[i]:clients() > 0 then
					targetTag = tags[i]
					break
				end
			end
		end
	end

	if targetTag then
		targetTag:view_only()
	end
end

function M.viewWorkspace(index)
	local s = awful.screen.focused()
	local t = s.tags[index]
	if t then
		-- toggles this tag on/off in the current view
		awful.tag.viewtoggle(t)
	end
end

function M.moveWindowToWorkspace(index)
	local c = client.focus
	local s = awful.screen.focused()
	local t = s.tags[index]
	if c and t then
		c:move_to_tag(t)
		t:view_only()
	end
end

--------------------------------
-- Window Focus / Mouse Centering
--------------------------------

function M.centerMouseOnFocusedClient()
	local c = client.focus
	if c then
		local geometry = c:geometry()
		local x = geometry.x + geometry.width / 2
		local y = geometry.y + geometry.height / 2
		mouse.coords({ x = x, y = y }, true)
	end
end

local function onNewWindow(callback)
	local existingClients = client.get()
	local timer = gears.timer({ timeout = 0.1 })
	timer:connect_signal("timeout", function()
		local currentClients = client.get()
		if #currentClients > #existingClients then
			for _, c in ipairs(currentClients) do
				if not gears.table.hasitem(existingClients, c) then
					timer:stop()
					callback(c)
					break
				end
			end
		end
		existingClients = currentClients
	end)
	timer:start()
end

function M.centerMouseOnNewWindow()
	onNewWindow(function(c)
		M.centerMouseOnFocusedClient()
	end)
end

function M.moveFocus(direction)
	awful.client.focus.bydirection(direction)
	M.centerMouseOnFocusedClient()
end

function M.swapWindow(direction)
	awful.client.swap.bydirection(direction)
	gears.timer.delayed_call(M.centerMouseOnFocusedClient)
end

--------------------------------
-- Volume / Multimedia
--------------------------------

function M.volumeControl(action, percentage)
	percentage = tostring(percentage) or "1"
	if action == "up" then
		awful.spawn("pactl set-sink-volume @DEFAULT_SINK@ +" .. percentage .. "%", false)
	elseif action == "down" then
		awful.spawn("pactl set-sink-volume @DEFAULT_SINK@ -" .. percentage .. "%", false)
	elseif action == "mute" then
		awful.spawn("playerctl play-pause", false)
	end
	bar.updateVolumeWidget()
end

--------------------------------
-- Layout
--------------------------------

function M.nextLayoutForTag()
	local a = awful.layout.suit
	local l = lain.layout

	local tagLayouts = {
		["Entertainment"] = { l.centerwork, a.tile, a.magnifier },
		["Code"] = { l.centerwork, a.fair, a.spiral.dwindle },
		["Work"] = { l.centerwork, a.spiral.dwindle, a.magnifier, l.cascade.tile },
		["Obsidian"] = { l.centerwork, l.cascade.tile },
		["Misc"] = { a.fair, a.floating },
	}

	local screen = awful.screen.focused()
	local tag = screen.selected_tag
	if not tag then
		return
	end

	local layouts = tagLayouts[tag.name]
	if not layouts then
		return
	end

	local currentLayout = tag.layout
	local currentIndex = gears.table.hasitem(layouts, currentLayout)
	if not currentIndex then
		tag.layout = layouts[1]
	else
		local nextIndex = (currentIndex % #layouts) + 1
		tag.layout = layouts[nextIndex]
	end
end

function M.promoteFocusedWindow(c)
	c = c or client.focus
	if c == awful.client.getmaster() then
		-- Already master: toggle maximized
		c.maximized = not c.maximized
		c.wasPromoted = c.maximized -- Only “true” if now maximized
		gears.timer.delayed_call(M.centerMouseOnFocusedClient)
		c:raise()
	else
		-- Not master yet: swap into master
		c:swap(awful.client.getmaster())
		c.wasPromoted = true -- Mark this as a “promoted” window
		gears.timer.delayed_call(M.centerMouseOnFocusedClient)
	end
end

function M.modifyMasterWidth(delta)
	awful.tag.incmwfact(delta)
end

--------------------------------
-- Save and load workspace configurations
--------------------------------

--------------------------------------------------------------------------------
-- Helper: Serialize a Lua table to a human-readable string.
--------------------------------------------------------------------------------
function M.serializeTable(val, name, depth)
	depth = depth or 0
	local indent = string.rep("  ", depth)
	local ret = ""
	if name then
		ret = ret .. indent .. string.format("[%q] = ", tostring(name))
	end
	if type(val) == "table" then
		ret = ret .. "{\n"
		for k, v in pairs(val) do
			ret = ret .. M.serializeTable(v, tostring(k), depth + 1) .. ",\n"
		end
		ret = ret .. indent .. "}"
	elseif type(val) == "string" then
		ret = ret .. string.format("%q", val)
	else
		ret = ret .. tostring(val)
	end
	return ret
end

--------------------------------------------------------------------------------
-- Save Workspace Configuration:
-- Saves the current tag’s layout (by name), master width factor, and tiling order
-- (cycling through clients starting at the master) to a file.
--------------------------------------------------------------------------------
function M.saveWorkspaceConfiguration(optionalFilename)
	local s = awful.screen.focused()
	local t = s.selected_tag
	if not t then
		return nil
	end

	local order = {}
	local master = awful.client.getmaster() or t:clients()[1]
	if not master then
		return nil
	end
	local origFocus = client.focus
	client.focus = master
	order[1] = { class = master.class or "", name = master.name or "" }
	local current = master
	repeat
		awful.client.focus.byidx(1)
		current = client.focus
		if current and current ~= master then
			table.insert(order, { class = current.class or "", name = current.name or "" })
		end
	until current == master
	if origFocus then
		client.focus = origFocus
	end

	local layoutName = "unknown"
	for _, mapping in ipairs(layoutMapping) do
		if t.layout == mapping.func then
			layoutName = mapping.name
			break
		end
	end

	local config = {
		workspace = optionalFilename or "",
		layoutName = layoutName,
		master_width_factor = t.master_width_factor,
		windowOrder = order,
	}

	local folder = os.getenv("HOME") .. "/.config/awesome/workspaces/"
	os.execute("mkdir -p " .. folder)
	if optionalFilename then
		if not optionalFilename or optionalFilename == "" then
			return
		end
		config.workspace = optionalFilename
		local serialized = M.serializeTable(config, nil, 0)
		local filename = folder .. optionalFilename .. ".lua"
		local file = io.open(filename, "w")
		if file then
			file:write("return " .. serialized)
			file:close()
		end
	else
		awful.prompt.run({
			prompt = "Save workspace configuration as: ",
			textbox = s.mypromptbox.widget,
			exe_callback = function(input)
				if not input or input == "" then
					return
				end
				config.workspace = input
				local serialized = M.serializeTable(config, nil, 0)
				local filename = folder .. input .. ".lua"
				local file = io.open(filename, "w")
				if file then
					file:write("return " .. serialized)
					file:close()
				end
			end,
		})
	end
end

--------------------------------------------------------------------------------
-- Compare and Reorder:
-- Compares the saved window order (target) with the current tiling order on a tag,
-- swapping windows as needed so that the order matches the saved order.
--------------------------------------------------------------------------------
function M.compareAndReorder(savedOrder, t)
	-- Extract numeric keys from savedOrder, then sort them in descending order.
	local savedKeys = {}
	for k in pairs(savedOrder) do
		table.insert(savedKeys, tonumber(k))
	end

	table.sort(savedKeys)

	-- We'll iterate through whichever list is shorter (assuming same size, though).
	local len = #savedKeys
	naughty.notify({ text = "Number of windows: " .. tostring(len) })
	client.focus = awful.client.getmaster()
	for index = 1, len do
		local savedKey = savedKeys[index]
		local desiredClass = savedOrder[tostring(savedKey)].class
		repeat
			awful.client.focus.byidx(1)
		until client.focus.class == desiredClass
		awful.client.setslave(client.focus)
	end
end

--------------------------------------------------------------------------------
-- Load Workspace Configuration:
-- Creates (or reuses) a tag with the saved layout and master width factor.
-- If a tag with the target workspace name already exists, its clients are moved
-- to an Overflow tag (volatile). Then, windows are moved (or spawned) onto the target tag.
-- Finally, the current order is saved to a compare file (with "_compare" appended)
-- and that compare order is compared with the saved order to swap windows as needed.
--------------------------------------------------------------------------------
function M.loadWorkspaceConfiguration(optionalFilename)
	local folder = os.getenv("HOME") .. "/.config/awesome/workspaces/"
	local wsName = optionalFilename -- assume optionalFilename is the workspace name (without extension)
	local function loadOrder(file, wsName)
		local config = dofile(file)
		local s = awful.screen.focused()
		local workspaceName = wsName or config.workspace or "LoadedWorkspace"

		-- Determine the layout function using our mapping table.
		local layoutFunc = awful.layout.layouts[1]
		for _, mapping in ipairs(layoutMapping) do
			if mapping.name:lower() == (config.layoutName or ""):lower() then
				layoutFunc = mapping.func
				break
			end
		end

		-- Create (or get) the Overflow tag first.
		local overflowTag = awful.tag.find_by_name(s, "Overflow")
		if not overflowTag then
			overflowTag = awful.tag.add("Overflow", {
				screen = s,
				layout = awful.layout.suit.fair,
				volatile = true,
			})
		end
		-- If a tag with the target workspace name exists, move its windows to Overflow.
		local targetTag = awful.tag.find_by_name(s, workspaceName)
		if targetTag then
			for _, c in ipairs(targetTag:clients()) do
				c:move_to_tag(overflowTag)
			end
		else
			targetTag = awful.tag.add(workspaceName, {
				screen = s,
				layout = layoutFunc,
			})
		end

		targetTag.master_width_factor = config.master_width_factor or targetTag.master_width_factor

		-- STEP 1: Spawn any missing windows on the Overflow tag, accounting for duplicates.
		overflowTag:view_only()
		local savedCounts = {}
		for _, winRec in pairs(config.windowOrder) do
			savedCounts[winRec.class] = (savedCounts[winRec.class] or 0) + 1
		end

		local currentCounts = {}
		for _, c in ipairs(overflowTag:clients()) do
			if c.class then
				currentCounts[c.class] = (currentCounts[c.class] or 0) + 1
			end
		end

		for class, savedCount in pairs(savedCounts) do
			local currentCount = currentCounts[class] or 0
			if currentCount < savedCount then
				local missing = savedCount - currentCount
				local cmd = defaultApps[class:lower()] or class:lower()
				for i = 1, missing do
					M.openNew(cmd, overflowTag)
				end
			end
		end

		-- STEP 1.5: Wait until all required windows have spawned on the Overflow tag.
		local function waitForAllWindows()
			local freqFound = {}
			for _, c in ipairs(overflowTag:clients()) do
				freqFound[c.class] = (freqFound[c.class] or 0) + 1
			end
			for class, reqCount in pairs(savedCounts) do
				local curCount = freqFound[class] or 0
				if curCount < reqCount then
					return false
				end
			end
			return true
		end

		gears.timer.start_new(0.1, function()
			if not waitForAllWindows() then
				return true -- continue polling
			end
			-- Once all windows are present, proceed to STEP 2.
			-- Before STEP 2: Order the saved window order as a numeric sequence.
			local orderedWindowOrder = {}
			for k, v in pairs(config.windowOrder) do
				local idx = tonumber(k)
				if idx then
					table.insert(orderedWindowOrder, { index = idx, winRec = v })
				end
			end
			table.sort(orderedWindowOrder, function(a, b)
				return a.index < b.index
			end)

			-- STEP 2: Move matching windows from the Overflow tag (overflowTag) to the target tag.
			local usedClients = {}
			for _, entry in ipairs(orderedWindowOrder) do
				local winRec = entry.winRec
				local found = nil
				-- First, try an exact match: class and name.
				for _, c in ipairs(overflowTag:clients()) do
					if not usedClients[c] and c.class == winRec.class and c.name == winRec.name then
						found = c
						usedClients[c] = true
						break
					end
				end
				-- If no exact match, try matching by class only.
				if not found then
					for _, c in ipairs(overflowTag:clients()) do
						if not usedClients[c] and c.class == winRec.class then
							found = c
							usedClients[c] = true
							break
						end
					end
				end
				if found then
					found:move_to_tag(targetTag)
					awful.client.setslave(found)
				end
			end
		end)
		targetTag:view_only()
		local function isMasterFocused()
			current = client.focus
			if current ~= awful.client.getmaster() then
				awful.client.focus.byidx(1)
			else
				return true
			end
		end
		gears.timer.start_new(0.1, function()
			if not isMasterFocused() then
				return true -- continue polling
			end
		end)
		gears.timer.delayed_call(M.centerMouseOnFocusedClient)
	end

	local folder = os.getenv("HOME") .. "/.config/awesome/workspaces/"
	local fullpath = folder .. wsName .. ".lua"
	loadOrder(fullpath, wsName)
end

--------------------------------
-- App Launching
--------------------------------

function M.openBrowser()
	awful.spawn("zen-browser")
end

function M.openFileManager()
	awful.spawn.with_shell("QT_QPA_PLATFORMTHEME=qt5ct QT_STYLE_OVERRIDE=kvantum dolphin")
end

function M.openEditor()
	awful.spawn("vscodium")
end

function M.openRofi(mode)
	local mode = mode or '-show combi -modes combi -combi-modes "window,drun,run" -terminal alacritty'
	awful.spawn("rofi " .. mode)
	M.centerMouseOnNewWindow()
end

function M.openNew(appCmd, targetTag)
	awful.spawn.with_shell(appCmd)
	if targetTag then
		local function manage_callback(c)
			if not c._moved then
				c:move_to_tag(targetTag)
				c._moved = true
				client.disconnect_signal("manage", manage_callback)
				gears.timer.delayed_call(M.centerMouseOnNewWindow)
			end
		end
		client.connect_signal("manage", manage_callback)
	else
		gears.timer.delayed_call(M.centerMouseOnNewWindow)
	end
end

-- Tap:  scope = "current"
-- Hold: scope = "all"
function M.findExisting(app, appCmd, scope)
	local appCmd = appCmd or app
	local scope = scope or "current"
	local lowerCmd = (app or ""):lower()
	local matchedClient

	local function matches(c)
		return ((c.class or ""):lower()):match(lowerCmd)
	end

	-- Fast path: if the focused client matches, promote and bail
	local fc = client.focus
	if fc and matches(fc) then
		M.promoteFocusedWindow(fc)
		return
	end

	-- Phase 1: search clients on the current selected tag(s)
	local currentTags = awful.screen.focused().selected_tags or {}
	for _, tag in ipairs(currentTags) do
		for _, c in ipairs(tag:clients()) do
			if matches(c) then
				matchedClient = c
				break
			end
		end
		if matchedClient then
			break
		end
	end

	-- If found on current tags, just focus/raise
	if matchedClient then
		if client.focus == matchedClient then
			M.promoteFocusedWindow(matchedClient)
		else
			client.focus = matchedClient
			matchedClient:raise()
			gears.timer.delayed_call(M.centerMouseOnFocusedClient)
		end
		return
	end

	-- Phase 2 (optional): search all tags if scope == "all"
	if scope == "all" then
		for _, c in ipairs(client.get()) do
			if matches(c) then
				matchedClient = c
				break
			end
		end

		if matchedClient then
			local t = matchedClient.first_tag
			if t then
				t:view_only()
			end
			client.focus = matchedClient
			matchedClient:raise()
			gears.timer.delayed_call(M.centerMouseOnFocusedClient)
			return
		end
	end

	-- Not found: launch new
	-- For taps, ensure spawn lands on the current primary selected tag
	local targetTag = nil
	if scope == "current" then
		targetTag = awful.screen.focused().selected_tag
	end
	M.openNew(appCmd, targetTag)
end

local dropdown_class = "Dropdown"

function M.toggleDropdownTerminal()
	local dropdown
	for _, c in ipairs(client.get()) do
		if c.class == dropdown_class then
			dropdown = c
			break
		end
	end

	if not dropdown then
		awful.spawn("alacritty --class 'Dropdown' -e tmux new-session -A -s dropdown", {
			floating = true,
			tag = awful.screen.focused().selected_tag,
		})
		return
	end

	local current_tag = awful.screen.focused().selected_tag

	if dropdown.hidden == true then
		dropdown.hidden = false
		dropdown.minimized = false
		dropdown:move_to_tag(current_tag)
		client.focus = dropdown
		dropdown:raise()
	elseif dropdown.first_tag == current_tag then
		dropdown.hidden = true
	else
		dropdown:move_to_tag(current_tag)
		client.focus = dropdown
		dropdown:raise()
	end
end

--------------------------------
-- Misc
--------------------------------

function M.lockScreen()
	awful.spawn("xset dpms force standby")
end

function M.showCheatsheet()
	hotkeys_popup.show_help(nil, awful.screen.focused())
end

function M.screenshot(full)
	if full then
		awful.spawn("flameshot full -c")
	else
		awful.spawn("flameshot gui")
	end
end

-- Change to the path of your Obsidian planner file
local obsidianInboxFile = "/home/max/Documents/The Vault/Notes/Personal/e-matrix.md"

-- Inserts a new item into the Inbox section
function M.insertItemIntoInbox(item)
	-- Read file
	local f = io.open(obsidianInboxFile, "r")
	if not f then
		naughty.notify({ title = "Error", text = "Could not open " .. obsidianInboxFile })
		return
	end

	local lines = {}
	for line in f:lines() do
		table.insert(lines, line)
	end
	f:close()

	-- Find "## Inbox" and the boundary for its section
	local startIndex, endIndex = nil, nil
	for i, line in ipairs(lines) do
		if line:match("^## Inbox$") then
			startIndex = i
			break
		end
	end

	if not startIndex then
		naughty.notify({ title = "Error", text = "'## Inbox' section not found in file." })
		return
	end

	for j = startIndex + 1, #lines do
		if lines[j]:match("^## ") then
			endIndex = j
			break
		end
	end

	if not endIndex then
		endIndex = #lines + 1
	end

	-- Insert new to-do
	table.insert(lines, endIndex, "- [ ] " .. item)

	-- Write back
	f = io.open(obsidianInboxFile, "w")
	if not f then
		naughty.notify({ title = "Error", text = "Unable to write back to " .. obsidianInboxFile })
		return
	end

	for _, line in ipairs(lines) do
		f:write(line .. "\n")
	end
	f:close()

	naughty.notify({ title = "Inbox Updated", text = "Added: " .. item })
end

-- Prompts the user for a to-do item in a centered floating window
function M.addInboxTodo()
	local focusedScreen = awful.screen.focused()

	-- Create a centered wibox
	local promptWibox = wibox({
		screen = focusedScreen,
		width = 400,
		height = 80,
		ontop = true,
		type = "dialog",
		visible = false,
		shape = gears.shape.rounded_rect,
		bg = "#1F2430", -- Adjust as needed
	})

	awful.placement.centered(promptWibox, { parent = focusedScreen })

	local promptWidget = awful.widget.prompt()
	promptWidget.font = "Terminus 24"
	-- Layout of the wibox
	promptWibox:setup({
		{
			{
				promptWidget,
				widget = wibox.container.margin,
				margins = 10,
			},
			layout = wibox.layout.flex.horizontal,
		},
		layout = wibox.layout.flex.vertical,
	})
	promptWidget.font = "Terminus 24"
	promptWibox.visible = true

	-- The actual prompt
	awful.prompt.run({
		prompt = "Add to Inbox: ",
		textbox = promptWidget.widget,
		exe_callback = function(input)
			promptWibox.visible = false

			if not input or #input == 0 then
				naughty.notify({ title = "Inbox", text = "No TODO entered." })
				return
			end

			M.insertItemIntoInbox(input)
		end,
		done_callback = function()
			promptWibox.visible = false
		end,
	})
end -- Done.

function M.bitwardenPasswordCLI()
	awful.spawn.with_shell("bash ~/.config/bitwarden/bitwardenRofi.sh")
end

function M.saveAndRestart()
	local path = os.getenv("HOME") .. "/.cache/awesomewm-last-tag"
	local scr = awful.screen.focused()
	local tag = scr.selected_tag

	if tag and scr then
		local f = io.open(path, "w")
		if f then
			f:write(string.format("%d %d\n", tag.index, scr.index))
			f:close()
		else
			naughty.notify({
				preset = naughty.config.presets.critical,
				title = "AwesomeWM",
				text = "❌ Could not write tag restore file.",
			})
			return
		end
	end

	awesome.restart()
end

function M.chooseWallpaper(random)
	if random then
		awful.spawn.with_shell("bash ~/Scripts/chooseWallpaper.sh true")
	else
		awful.spawn.with_shell("bash ~/Scripts/chooseWallpaper.sh")
	end
end

function M.pasteFromHistory()
	awful.spawn.with_shell("bash ~/Scripts/pasteFromHistory.sh")
end

function M.startDroidCam()
	awful.spawn.with_shell("droidcam-cli -size=3840x2160 192.168.0.156 4747")
end
return M
