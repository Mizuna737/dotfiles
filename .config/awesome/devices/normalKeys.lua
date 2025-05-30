-- normalKeys.lua
-- Non-device (i.e., standard keyboard) hotkeys.

local gears = require("gears")
local awful = require("awful")
local myFuncs = require("functions")
local stack = require("stack")
local defaultApps = require("defaultApps")

local modkey = "Mod4"
local altkey = "Mod1"

local normalKeys = {}

normalKeys.globalkeys = gears.table.join(

	-- Volume

	awful.key({}, "XF86AudioRaiseVolume", function()
		myFuncs.volumeControl("up", 1)
	end, { description = "increase volume", group = "volume" }),

	awful.key({}, "XF86AudioLowerVolume", function()
		myFuncs.volumeControl("down", 1)
	end, { description = "decrease volume", group = "volume" }),

	awful.key({ "Shift" }, "XF86AudioRaiseVolume", function()
		myFuncs.volumeControl("up", 5)
	end, { description = "increase volume", group = "volume" }),

	awful.key({ "Shift" }, "XF86AudioLowerVolume", function()
		myFuncs.volumeControl("down", 5)
	end, { description = "decrease volume", group = "volume" }),

	awful.key({}, "XF86AudioMute", function()
		myFuncs.volumeControl("mute")
	end, { description = "toggle mute", group = "volume" }),

	-- Change Master Width

	awful.key({ modkey }, "XF86AudioRaiseVolume", function()
		myFuncs.modifyMasterWidth(0.005)
	end, { description = "increase mwf", group = "layout" }),

	awful.key({ modkey }, "XF86AudioLowerVolume", function()
		myFuncs.modifyMasterWidth(-0.005)
	end, { description = "decrease mwf", group = "layout" }),

	awful.key({ modkey, "Shift" }, "XF86AudioRaiseVolume", function()
		myFuncs.modifyMasterWidth(0.02)
	end, { description = "increase mwf", group = "layout" }),

	awful.key({ modkey, "Shift" }, "XF86AudioLowerVolume", function()
		myFuncs.modifyMasterWidth(-0.02)
	end, { description = "decrease mwf", group = "layout" }),

	-- Clipboard

	awful.key({ modkey }, "v", function()
		myFuncs.pasteFromHistory()
	end),

	-- Launch apps

	awful.key({ modkey }, "Return", function()
		myFuncs.findExisting(defaultApps.terminal, defaultApps.terminalCommand)
	end, { description = "open terminal", group = "launcher" }),

	awful.key({ modkey, altkey }, "Return", function()
		myFuncs.findExisting(defaultApps.editor, defaultApps.editorCommand)
	end, { description = "open editor", group = "launcher" }),

	awful.key({ modkey }, "q", function()
		myFuncs.openBrowser()
		myFuncs.centerMouseOnNewWindow()
	end, { description = "open browser", group = "launcher" }),

	-- Rofi

	awful.key({ modkey }, "space", function()
		myFuncs.openRofi()
	end, { description = "open browser", group = "launcher" }),

	-- Dropdown terminal

	awful.key({ modkey }, "t", function()
		myFuncs.toggleDropdownTerminal()
	end, { description = "dropdown terminal", group = "launcher" }),

	-- bitwardenCLI interface

	awful.key({ modkey }, "p", function()
		myFuncs.bitwardenPasswordCLI()
	end, { description = "bitwardenPasswordCLI", group = "launcher" }),

	-- Choose Wallpaper

	awful.key({ modkey }, "w", function()
		myFuncs.chooseWallpaper()
	end, { description = "choose wallpaper and theme" }),

	awful.key({ modkey, altkey }, "w", function()
		myFuncs.chooseWallpaper(true)
	end, { description = "choose random wallpaper and theme" }),

	-- Layout switching

	awful.key({ altkey }, "space", function()
		myFuncs.nextLayoutForTag()
	end, { description = "cycle layouts for current tag", group = "layout" }),

	-- Tag navigation

	awful.key({ modkey }, "Left", awful.tag.viewprev, { description = "view previous tag", group = "tag" }),

	awful.key({ modkey }, "Right", awful.tag.viewnext, { description = "view next tag", group = "tag" }),

	-- Next/previous populated tag

	awful.key({ modkey }, "Page_Up", function()
		myFuncs.viewPopulatedTag("previous")
	end, { description = "view prev populated tag", group = "tag" }),

	awful.key({ modkey }, "Page_Down", function()
		myFuncs.viewPopulatedTag("next")
	end, { description = "view next populated tag", group = "tag" }),

	-- Focus windows

	awful.key({ modkey }, "j", function()
		myFuncs.moveFocus("down")
	end, { description = "focus down", group = "client" }),

	awful.key({ modkey }, "k", function()
		myFuncs.moveFocus("up")
	end, { description = "focus up", group = "client" }),

	awful.key({ modkey }, "h", function()
		myFuncs.moveFocus("left")
	end, { description = "focus left", group = "client" }),

	awful.key({ modkey }, "l", function()
		myFuncs.moveFocus("right")
	end, { description = "focus right", group = "client" }),

	-- Stack extension

	awful.key({ modkey, "Shift" }, "n", function()
		local c = client.focus
		if c then
			stack.stackClients(c)
		end
	end, { description = "stack client with next", group = "Stacking" }),

	awful.key({ modkey, "Shift" }, "l", function()
		stack.listStacks()
	end, { description = "list all stacks", group = "Stacking" }),

	awful.key({ modkey, "Shift" }, "c", function()
		stack.clearStacks()
	end, { description = "clear all stacks", group = "Stacking" }),

	awful.key({ modkey, "Shift" }, "u", function()
		stack.cycleStack()
	end, { description = "cycle stack", group = "Stacking" }),

	-- Reload / Quit Awesome

	awful.key({ modkey, "Control" }, "r", function()
		myFuncs.saveAndRestart()
	end, { description = "reload awesome", group = "awesome" }),

	awful.key({ modkey, "Shift" }, "q", awesome.quit, { description = "quit awesome", group = "awesome" })
)

-- Client-specific keys
normalKeys.clientkeys = gears.table.join(

	awful.key({ modkey }, "f", function(c)
		c.fullscreen = not c.fullscreen
		c:raise()
	end, { description = "toggle fullscreen", group = "client" }),

	awful.key({ modkey }, "Escape", function(c)
		c:kill()
		gears.timer.start_new(0.1, function()
			myFuncs.centerMouseOnFocusedClient()
			return false
		end)
	end, { description = "close", group = "client" }),

	awful.key(
		{ modkey, "Control" },
		"space",
		awful.client.floating.toggle,
		{ description = "toggle floating", group = "client" }
	),

	awful.key({ modkey, "Control" }, "Return", function(c)
		myFuncs.promoteFocusedWindow(c)
	end, { description = "swap/maximize if master", group = "client" })
)

return normalKeys
