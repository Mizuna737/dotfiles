-- rc.lua
-- Main AwesomeWM orchestration: theme, autostart, rules, plus merging all device + normal keys.

pcall(require, "luarocks.loader") -- If LuaRocks is installed, ensure packages are loaded.

-- Required libraries
local gears = require("gears")
local awful = require("awful")
require("awful.autofocus")
local beautiful = require("beautiful")
local naughty = require("naughty")
local lain = require("lain")

-- Error handling
if awesome.startup_errors then
	naughty.notify({
		preset = naughty.config.presets.critical,
		title = "Oops, there were errors during startup!",
		text = awesome.startup_errors,
	})
end

do
	local in_error = false
	awesome.connect_signal("debug::error", function(err)
		if in_error then
			return
		end
		in_error = true
		naughty.notify({
			preset = naughty.config.presets.critical,
			title = "Oops, an error happened!",
			text = tostring(err),
		})
		in_error = false
	end)
end

--------------------------------
-- Autostart
--------------------------------

local function runOnce(cmd_arr)
	for _, cmd in ipairs(cmd_arr) do
		awful.spawn.with_shell(string.format("pgrep -u $USER -fx '%s' > /dev/null || (%s)", cmd, cmd))
	end
end

runOnce({
	"urxvtd",
	"hhpc -i 1",
	"~/.screenlayout/DefaultLayout.sh",
	"lxqt=policykit-agent",
	"copyq",
	"windscribe-cli connect",
})

awful.spawn.with_shell(
	'if (xrdb -query | grep -q "^awesome\\.started:\\s*true$"); then exit; fi;'
		.. 'xrdb -merge <<< "awesome.started:true";'
		.. "dex --environment Awesome --autostart --search-paths "
		.. '"${XDG_CONFIG_HOME:-$HOME/.config}/autostart:${XDG_CONFIG_DIRS:-/etc/xdg}/autostart";'
)

awful.spawn.with_shell("zsh ~/Scripts/dpmsInhibit.sh")

--------------------------------
-- Theme & Layout
--------------------------------

beautiful.init("/home/max/.config/awesome/themes/powerarrow/theme.lua")
--------------------------------
-- Wibar
--------------------------------

local bar = require("bar") -- Adjust if bar.lua is in a subfolder
local workspaceManager = require("workspaceManager")
bar.setupWibar()

--------------------------------
-- Tag Setup
--------------------------------

awful.util.primaryTagnames = { "Entertainment", "Code", "Work", "Obsidian", "Misc" }

-- Layout Mapping Table
layoutMapping = {
	{ func = awful.layout.suit.tile, name = "tile" },
	{ func = awful.layout.suit.tile.left, name = "tileleft" },
	{ func = awful.layout.suit.tile.bottom, name = "tilebottom" },
	{ func = awful.layout.suit.tile.top, name = "tiletop" },
	{ func = awful.layout.suit.fair, name = "fair" },
	{ func = awful.layout.suit.fair.horizontal, name = "fairhorizontal" },
	{ func = awful.layout.suit.spiral, name = "spiral" },
	{ func = awful.layout.suit.spiral.dwindle, name = "dwindle" },
	{ func = awful.layout.suit.max, name = "max" },
	{ func = awful.layout.suit.fullscreen, name = "fullscreen" },
	{ func = awful.layout.suit.magnifier, name = "magnifier" },
	{ func = awful.layout.suit.floating, name = "floating" },
	{ func = lain.layout.centerwork, name = "centerwork" },
	{ func = lain.layout.termfair, name = "termfair" },
	{ func = lain.layout.cascade.tile, name = "cascade_tile" },
	{ func = lain.layout.cascade, name = "cascade" },
}
-- Basic layout definitions for each tag
local primaryLayoutFallbacks = {
	lain.layout.centerwork,
	lain.layout.centerwork,
	lain.layout.centerwork,
	lain.layout.centerwork,
	awful.layout.suit.fair,
}
awful.layout.primaryLayouts = {}
for i, tagName in ipairs(awful.util.primaryTagnames) do
	awful.layout.primaryLayouts[i] = workspaceManager.getSavedLayout(tagName) or primaryLayoutFallbacks[i]
end

local primary_tags = awful.tag(awful.util.primaryTagnames, screen.primary, awful.layout.primaryLayouts)

-- Dashboard screen: single locked tag
-- Also handles late connection (HDMI-0 often not enumerated when rc.lua first runs)
local dashboardScreen = nil

local function setupDashboardScreen(s)
	if s == screen.primary then
		return
	end
	dashboardScreen = s
	if #s.tags == 0 then
		awful.tag({ "Dashboard" }, s, awful.layout.suit.max)
	end
	-- Reapply wallpaper so the newly-connected screen gets it
	awful.spawn.with_shell("[ -f ~/.fehbg ] && ~/.fehbg")

	-- Delay 1s to let AwesomeWM fully initialise the new screen before
	-- attempting to place or launch the dashboard.
	gears.timer.start_new(1, function()
		local dashTag = awful.tag.find_by_name(s, "Dashboard")
		if not dashTag then
			dashTag = awful.tag({ "Dashboard" }, s, awful.layout.suit.max)[1]
		end

		local existingDash = nil
		for _, c in ipairs(client.get()) do
			if c.class == "dashboard" then
				existingDash = c
				break
			end
		end

		if existingDash then
			if existingDash.screen ~= s then
				existingDash:move_to_tag(dashTag)
			end
		else
			awful.spawn.with_shell("bash ~/.config/dashboard/dashboardLaunch.sh")
		end
		return false
	end)
end

for s in screen do
	setupDashboardScreen(s)
end

screen.connect_signal("added", setupDashboardScreen)

-- Retry DefaultLayout.sh every 3s (up to 5x) if HDMI-0 isn't detected at startup
local screenRetries = 0
gears.timer.start_new(3, function()
	for s in screen do
		if s ~= screen.primary then
			return false -- secondary screen found, stop retrying
		end
	end
	awful.spawn.with_shell("~/.screenlayout/DefaultLayout.sh")
	screenRetries = screenRetries + 1
	return screenRetries < 5
end)

--------------------------------
-- Custom layout settings
--------------------------------

primary_tags[1].master_width_factor = 0.694

--------------------------------
-- Load Our Custom Logic & Modules
--------------------------------

local myFuncs = require("functions") -- custom functions
local micWatcher = require("micWatcher")
local glowBorder = require("glowBorder")
local stack = require("stack") -- your separate stacking module
require("signals") -- gesture D-Bus signal handlers
local normalKeys = require("devices.normalKeys") -- normal (keyboard) hotkeys

-- Device-specific keymaps
local tartarusKeys = require("devices.tartarus")
local scimitarKeys = require("devices.scimitar")
-- local streamdeckKeys= require("devices.streamdeck")
local macropadKeys = require("devices.macropad")

--------------------------------
-- Combine All Keybinds
--------------------------------

local gears_table_join = gears.table.join

local globalkeys = gears_table_join(
	normalKeys.globalkeys,
	tartarusKeys.globalkeys,
	scimitarKeys.globalkeys,
	-- streamdeckKeys.globalkeys,
	macropadKeys.globalkeys
)

-- Optionally combine client keys from normalKeys (and more if needed)
local clientkeys = gears_table_join(
	normalKeys.clientkeys
	-- e.g. tartarusKeys.clientkeys, scimitarKeys.clientkeys, etc., if you define them
)

local clientbuttons = awful.util.table.join(
	-- Move window on Meta + Left Click
	awful.button({ "Mod4" }, 1, awful.mouse.client.move),

	-- Resize window on Meta + Right Click
	awful.button({ "Mod4" }, 3, awful.mouse.client.resize)
)

root.keys(globalkeys)

--------------------------------
-- Rules
--------------------------------

awful.rules.rules = {
	{
		rule = {},
		properties = {
			border_width = beautiful.border_width,
			border_color = beautiful.border_normal,
			focus = awful.client.focus.filter,
			raise = true,
			keys = clientkeys,
			buttons = clientbuttons,
			screen = awful.screen.preferred,
			placement = awful.placement.no_overlap + awful.placement.no_offscreen,
			size_hints_honor = false,
		},
	},
	{
		rule = { class = "dashboard" },
		properties = {
			border_width = 0,
		},
		callback = function(c)
			if dashboardScreen and dashboardScreen.valid then
				local dashTag = awful.tag.find_by_name(dashboardScreen, "Dashboard")
				if dashTag then
					c:move_to_tag(dashTag)
				end
			end
		end,
	},
	{
		rule_any = {
			instance = { "DTA", "copyq", "pinentry" },
			class = {
				"Arandr",
				"Blueman-manager",
				"Gpick",
				"Kruler",
				"MessageWin",
				"Sxiv",
				"Tor Browser",
				"Wpa_gui",
				"veromix",
				"xtightvncviewer",
				"Windscribe2",
			},
			name = { "Event Tester" },
			role = { "AlarmWindow", "ConfigManager", "pop-up" },
		},
		properties = { floating = true },
	},
	-- Make nsxiv floating, centered, and large on the primary monitor
	{
		rule = { class = "Nsxiv" },
		properties = {
			floating = true,
			ontop = true,
			skip_taskbar = true,
			screen = screen.primary,
			focus = true,
		},
		callback = function(c)
			local g = screen.primary.workarea
			local width = math.floor(g.width * 0.9)
			local height = math.floor(g.height * 0.9)
			c:geometry({
				x = g.x + (g.width - width) / 2,
				y = g.y + (g.height - height) / 2,
				width = width,
				height = height,
			})
		end,
	},

	{
		rule_any = { type = { "normal", "dialog" } },
		properties = { titlebars_enabled = false },
	},
	{
		rule = { class = "Dropdown" },
		properties = {
			floating = true,
			width = 1000,
			height = 600,
			placement = awful.placement.centered,
			ontop = true,
			skip_taskbar = true,
		},
	},
	{
		rule = { class = "eisenhower" },
		properties = {
			ontop = true,
		},
	},
}

--------------------------------
-- Signals
--------------------------------

awesome.connect_signal("wal::reload", function()
	beautiful.init("/home/max/.config/awesome/themes/powerarrow/theme.lua")
	beautiful.useless_gap = 6
	for s in screen do
		if s ~= screen.primary then
			return
		end
		s.mywibox.bg = beautiful.bg_normal
	end
end)

client.connect_signal("manage", function(c)
	if awesome.startup and not c.size_hints.user_position and not c.size_hints.program_position then
		awful.placement.no_offscreen(c)
	end
end)

client.connect_signal("mouse::enter", function(c)
	c:emit_signal("request::activate", "mouse_enter", { raise = false })
end)

client.connect_signal("request::activate", function(c, context, hints)
	if not c:isvisible() then
		local t = c.first_tag
		if t then
			t:view_only()
		end
	end
end)

local function applyBorder(c)
	if not c or not c.valid then return end
	if client.focus ~= c then
		c.border_color = beautiful.border_normal
		return
	end
	if myFuncs.isCommsClient(c) then
		if micWatcher.muted then
			c.border_color = glowBorder.blend(beautiful.borderMutedBright, beautiful.borderMutedDim)
		else
			c.border_color = glowBorder.blend(beautiful.borderUnmutedBright, beautiful.borderUnmutedDim)
		end
	else
		c.border_color = glowBorder.blend(beautiful.border_focus, beautiful.border_normal)
	end
end

client.connect_signal("focus", function(c)
	applyBorder(c)
end)

client.connect_signal("unfocus", function(c)
	applyBorder(c)
	if c.wasPromoted and c.maximized then
		c.maximized = false
		c.wasPromoted = false
	end
end)

awesome.connect_signal("micMuteChanged", function()
	if client.focus then applyBorder(client.focus) end
end)

awesome.connect_signal("save::focused_tag", function()
	local scr = awful.screen.focused()
	local tag = scr.selected_tag
	if tag then
		local path = os.getenv("HOME") .. "/.cache/awesomewm-last-tag"
		local f = io.open(path, "w")
		if f then
			f:write(string.format("%d %d", tag.index, scr.index))
			f:close()
		else
			naughty.notify({
				preset = naughty.config.presets.critical,
				title = "Tag Save Failed",
				text = "Couldn't write to ~/.cache/awesomewm-last-tag",
			})
		end
	end
end)

local path = os.getenv("HOME") .. "/.cache/awesomewm-last-tag"
local f = io.open(path, "r")

if f then
	local tag_index, screen_index = f:read("*n", "*n")
	f:close()
	local scr = screen[screen_index]
	if scr and scr.tags and scr.tags[tag_index] then
		gears.timer.start_new(0.01, function()
			scr.tags[tag_index]:view_only()
			return false
		end)
	end
end

beautiful.useless_gap = 6

--------------------------------
-- Finish up
----------------------------------
bar.updateVolumeWidget()
micWatcher.start()
glowBorder.subscribe(function()
	if client.focus then applyBorder(client.focus) end
end)
glowBorder.start()

-- Done.
