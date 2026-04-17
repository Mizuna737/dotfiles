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

---------------------------------
-- Helpers
---------------------------------
function M.roundToNearest(nearest, n)
	return math.floor(n / nearest + 0.5) * nearest
end
---------------------------------
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

function M.viewWorkspaceExclusive(index)
	local s = awful.screen.focused()
	local t = s.tags[index]
	if t then
		t:view_only()
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

function M.focusMaster()
	local master = awful.client.getmaster()
	if master then
		client.focus = master
		master:raise()
		gears.timer.delayed_call(M.centerMouseOnFocusedClient)
	end
end

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
	elseif action == "set" then
		awful.spawn("pactl set-sink-volume @DEFAULT_SINK@ " .. percentage .. "%", false)
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

local commsForTag = {
	["Work"] = { app = "teams-for-linux", cmd = "teams-for-linux" },
	["Entertainment"] = { app = "discord", cmd = "discord" },
}

-- scope "current" = look on current tag, spawn if missing
-- scope "all"     = search across all tags, follow if found elsewhere
function M.findComms(scope)
	scope = scope or "current"
	local tag = awful.screen.focused().selected_tag
	local tagName = tag and tag.name or ""
	local info = commsForTag[tagName] or { app = "signal", cmd = "signal-desktop" }
	M.findExisting(info.app, info.cmd, scope)
end

function M.prevLayoutForTag()
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

	local currentIndex = gears.table.hasitem(layouts, tag.layout)
	if not currentIndex then
		tag.layout = layouts[#layouts]
	else
		tag.layout = layouts[((currentIndex - 2 + #layouts) % #layouts) + 1]
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

local workspaceManager = require("workspaceManager")
M.serializeTable = workspaceManager.serializeTable
M.saveWorkspaceConfiguration = workspaceManager.saveWorkspaceConfiguration
M.compareAndReorder = workspaceManager.compareAndReorder
M.loadWorkspaceConfiguration = workspaceManager.loadWorkspaceConfiguration

--------------------------------
-- App Control
--------------------------------

-- Helper: run after we "close"
local function postClose()
	gears.timer.start_new(0.1, function()
		if M.centerMouseOnFocusedClient then
			M.centerMouseOnFocusedClient()
		end
		return false
	end)
end

-- Helper: is this client one of our dropdown apps?
local function isDropdownClient(c)
	if not c or not c.valid then
		return false
	end
	if not M.dropdownClasses then
		return false
	end -- set by your dropdown module
	return c.class and M.dropdownClasses[c.class] == true
end

-- Smart close:
-- - Dropdown app: hide it
-- - Otherwise: if it looks like a terminal, try tmux detach, else kill
function M.smartCloseFocusedClient()
	local c = client.focus
	if not c or not c.valid then
		return
	end

	-- 1) Dropdown: hide instead of kill
	if isDropdownClient(c) then
		c.hidden = true
		postClose()
		return
	end

	-- 2) Default: kill the client
	c:kill()
	postClose()
end

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

-- Toggle a floating "dropdown" app by WM_CLASS.
-- opts = {
--   class = "Quick Notes",
--   spawn_cmd = "kitty --class 'Quick Notes' -e nvim -u NONE -U NONE --clean ~/Notes/quick.md",
--   spawn_props = { floating = true, tag = awful.screen.focused().selected_tag },
-- }
-- Track which WM_CLASS values we consider "dropdown apps"
M.dropdownClasses = {
	["Dropdown"] = true,
	["Quick Notes"] = true,
	-- add more here later
}
local function hideOtherDropdowns(except_class)
	for _, c in ipairs(client.get()) do
		if
			c.valid
			and c.class
			and M.dropdownClasses[c.class]
			and c.class ~= except_class
			and (c.hidden == false)
			and (c.minimized == false)
		then
			c.hidden = true
		end
	end
end

function M.toggleDropdownApp(opts)
	-- Position a dropdown window centered on the primary screen
	-- widthPct and heightPct are 0.0-1.0 fractions of the screen workarea
	local function positionDropdown(win, widthPct, heightPct)
		local s = screen.primary
		local wa = s.workarea
		local w = math.floor(wa.width * (widthPct or 0.3))
		local h = math.floor(wa.height * (heightPct or 0.6))
		win:geometry({
			x = wa.x + math.floor((wa.width - w) / 2),
			y = wa.y + math.floor((wa.height - h) / 2),
			width = w,
			height = h,
		})
	end
	local class = opts.class
	local spawn_cmd = opts.spawn_cmd
	local spawn_props = opts.spawn_props or {}

	-- Ensure class is registered
	M.dropdownClasses[class] = true

	local win
	for _, c in ipairs(client.get()) do
		if c.class == class then
			win = c
			break
		end
	end

	local current_tag = awful.screen.focused().selected_tag

	if not win then
		hideOtherDropdowns(class)
		if spawn_props.tag == nil then
			spawn_props.tag = current_tag
		end
		if spawn_props.floating == nil then
			spawn_props.floating = true
		end
		-- Hook manage signal to position on first spawn
		local function onManage(c)
			if c.class == class then
				positionDropdown(c, opts.widthPct, opts.heightPct)
				client.disconnect_signal("manage", onManage)
			end
		end
		client.connect_signal("manage", onManage)
		awful.spawn(spawn_cmd, spawn_props)
		return
	end
	-- If we're about to show/focus this dropdown, hide the others first
	local will_show = (win.hidden == true) or (win.minimized == true) or (win.first_tag ~= current_tag)
	if will_show then
		hideOtherDropdowns(class)
	end

	if win.hidden == true or win.minimized == true then
		win.hidden = false
		win.minimized = false
		win:move_to_tag(current_tag)
		positionDropdown(win, opts.widthPct, opts.heightPct)
		client.focus = win
		win:raise()
		win:emit_signal("request::activate", "dropdown", { raise = true })
	elseif win.first_tag == current_tag then
		if opts.closeOnHide then
			win:kill()
		else
			win.hidden = true
		end
	else
		win:move_to_tag(current_tag)
		client.focus = win
		win:raise()
		win:emit_signal("request::activate", "dropdown", { raise = true })
	end
end

function M.toggleEisenhower()
	M.toggleDropdownApp({
		class = "eisenhower",
		spawn_cmd = "bash /home/max/Scripts/eisenhower.sh",
		spawn_props = {
			floating = true,
			ontop = true,
			tag = awful.screen.focused().selected_tag,
		},
		widthPct = 0.3,
		heightPct = 0.6,
	})
end

function M.toggleQuickNotes()
	M.toggleDropdownApp({
		class = "Quick Notes",
		spawn_cmd = {
			"kitty",
			"--class",
			"Quick Notes",
			"--override",
			"font_size=18.0",
			"--override",
			"confirm_os_window_close=0",
			"-e",
			"bash",
			os.getenv("HOME") .. "/Scripts/quickNotes.sh",
		},
		spawn_props = { floating = true, tag = awful.screen.focused().selected_tag },
	})
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

-- Prompts the user for a to-do item in a centered floating window
function M.addInboxTodo()
	awful.spawn.with_shell("bash ~/Scripts/captureTask.sh")
end

function M.fileTasks()
	awful.spawn.with_shell("bash ~/Scripts/fileTasks.sh")
end

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

function M.toggleVPN()
	awful.spawn.with_shell("curl -s -X POST http://localhost:9876/toggle/vpn")
end

function M.cycleSink()
	awful.spawn.with_shell("curl -s -X POST http://localhost:9876/toggle/sink")
end

return M
