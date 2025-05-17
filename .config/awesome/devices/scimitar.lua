-- devices/scimitar.lua
-- The Corsair Scimitar with 12 side buttons.
-- We'll call them XF86Tools1..XF86Tools12 in keyd.
-- "Mouse-L2" might be Control on your keyboard to create a second layer.

local gears = require("gears")
local awful = require("awful")
local naughty = require("naughty")
local myFuncs = require("functions")
local stack = require("stack")
local defaultApps = require("defaultApps")
-- Modifiers:
local modkey = "Mod4" -- Super
local ctrl = "Control"
local altkey = "Mod1"
local shft = "Shift"

local scimitar = {}

--------------------------------
-- Helper function for brevity
--------------------------------
local function sk(mods, key, func, desc)
	return awful.key(mods, key, func, { description = desc, group = "scimitar" })
end

scimitar.globalkeys = gears.table.join(
	-- Key F1
	sk({ modkey, ctrl }, "F1", function()
		myFuncs.screenshot()
	end, "S1 tap => screenshot gui"),
	sk({ modkey, ctrl, shft }, "F1", function()
		myFuncs.screenshot(1)
	end, "S1 mod => full screen screenshot"),

	-- Key F2
	sk({ modkey, ctrl }, "F2", function()
		awful.spawn(defaultApps.browser)
	end, "S2 tap => open default browser"),
	sk({ modkey, ctrl, shft }, "F2", function()
		awful.spawn("google-chrome")
	end, "S2 mod => open chrome"),

	-- Key F3
	sk({ modkey, ctrl }, "F3", function()
		awful.spawn(defaultApps.terminal)
	end, "S3 tap => open terminal"),
	sk({ modkey, ctrl, shft }, "F3", function()
		awful.spawn(defaultApps.terminal .. " -e htop")
	end, "S3 mod => terminal with htop"),

	-- Key F4
	sk({ modkey, ctrl }, "F4", function()
		myFuncs.openLauncher()
	end, "S4 tap => open launcher"),
	sk({ modkey, ctrl, shft }, "F4", function()
		naughty.notify({ text = "S4 mod pressed" })
	end, "S4 mod => notify"),

	-- Key F5 (single layer only)
	sk({ modkey, ctrl }, "F5", function()
		myFuncs.promoteFocusedWindow()
	end, "S5 tap => promote focused window"),

	-- Key F6
	sk({ modkey, ctrl }, "F6", function()
		awful.spawn(defaultApps.filemgr)
	end, "S6 tap => open file manager"),
	sk({ modkey, ctrl, shft }, "F6", function()
		naughty.notify({ text = "S6 mod pressed" })
	end, "S6 mod => notify"),

	-- Key F7
	sk({ modkey, ctrl }, "F7", function()
		awful.spawn(defaultApps.editor)
	end, "S7 tap => open editor"),
	sk({ modkey, ctrl, shft }, "F7", function()
		naughty.notify({ text = "S7 mod pressed" })
	end, "S7 mod => notify"),

	-- Key F8
	sk({ modkey, ctrl }, "F8", function()
		myFuncs.toggleFloating()
	end, "S8 tap => toggle floating"),
	sk({ modkey, ctrl, shft }, "F8", function()
		naughty.notify({ text = "S8 mod pressed" })
	end, "S8 mod => notify"),

	-- Key F9
	sk({ modkey, ctrl }, "F9", function()
		myFuncs.cycleLayouts()
	end, "S9 tap => cycle layouts"),
	sk({ modkey, ctrl, shft }, "F9", function()
		naughty.notify({ text = "S9 mod pressed" })
	end, "S9 mod => notify"),

	-- Key F10
	sk({ modkey, ctrl }, "F10", function()
		myFuncs.bitwardenPasswordCLI()
	end, "S10 tap => bitwardenPasswordCLI"),
	sk({ modkey, ctrl, shft }, "F10", function()
		naughty.notify({ text = "S10 mod pressed" })
	end, "S10 mod => notify"),

	-- Key F11
	sk({ modkey, ctrl }, "F11", function()
		myFuncs.toggleScratchpad()
	end, "S11 tap => toggle scratchpad"),
	sk({ modkey, ctrl, shft }, "F11", function()
		naughty.notify({ text = "S11 mod pressed" })
	end, "S11 mod => notify"),

	-- Key F12
	sk({ modkey, ctrl }, "F12", function()
		awful.spawn(defaultApps.email)
	end, "S12 tap => open email client"),
	sk({ modkey, ctrl, shft }, "F12", function()
		naughty.notify({ text = "S12 mod pressed" })
	end, "S12 mod => notify")
)

return scimitar
