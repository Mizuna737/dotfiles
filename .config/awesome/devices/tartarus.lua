--------------------------------
-- tartarus.lua
-- Four actions per Tartarus key: tap, tap+hold, modified tap, modified tap+hold
-- Some keys have real actions; others do a naughty.notify placeholder.
--------------------------------

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

local tartarus = {}

--------------------------------
-- Helper function for brevity
--------------------------------
local function tk(mods, key, func, desc)
	return awful.key(mods, key, func, { description = desc, group = "tartarus" })
end

--------------------------------
-- Explanation:
-- Each physical key does:
--   Tap =>   (modkey + ctrl + KEY)
--   Tap+Hold => (modkey + ctrl + altkey + KEY)
--   Mod Tap => (modkey + ctrl + shft + KEY)
--   Mod Tap+Hold => (modkey + ctrl + altkey + shft + KEY)
--
-- The short vs. long press is handled by keyd overloadi,
-- and physically pressing T21 maps to "Shift" in keyd.
--------------------------------
--[[
  Tartarus Key Assignments (6-column table)
  
  Columns:
    1) Key # (1–20)
    2) Default Assignment (physical label)
    3) Tap (short press)
    4) Tap+Hold (long press)
    5) Modified Tap (short press + T21 modifier)
    6) Modified Tap+Hold (long press + T21 modifier)
  
  | #  | Default | Tap              | Tap+Hold               | Mod Tap                 | Mod Tap+Hold                |
  |----|---------|------------------|------------------------|-------------------------|-----------------------------|
  | 1  | 1       | Find Terminal    | Open Terminal          | View Tag 1              | Move Focused Window to 1    |
  | 2  | 2       | Find Browser     | Open Browser           | View Tag 2              | Move Focused Window to 2    |
  | 3  | 3       | Find Editor      | Open Editor            | View Tag 3              | Move Focused Window to 3    |
  | 4  | 4       | Find File Browser| Open File Browser      | View Tag 4              | Move Focused Window to 4    |                            |
  | 5  | 5       |                  |                        |                         |                             |
  | 6  | tab     |                  |                        |                         |                             |
  | 7  | q       |                  |                        |                         |                             |
  | 8  | w       |                  |                        |                         |                             |
  | 9  | e       |                  |                        |                         |                             |
  | 10 | r       |                  |                        |                         |                             |
  | 11 | caps    |                  |                        |                         |                             |
  | 12 | a       |                  |                        |                         |                             |
  | 13 | s       |                  |                        |                         |                             |
  | 14 | d       |                  |                        |                         |                             |
  | 15 | f       |                  |                        |                         |                             |
  | 16 | shift   |                  |                        |                         |                             |
  | 17 | z       |                  |                        |                         |                             |
  | 18 | x       |                  |                        |                         |                             |
  | 19 | c       |                  |                        |                         |                             |
  | 20 | space   |                  |                        |                         |                             |
]]
tartarus.globalkeys = gears.table.join(

	--------------------------------------------------
	-- Row 1: 1, 2, 3, 4, 5
	--------------------------------------------------

	-- Key 1
	tk({ modkey, ctrl }, "1", function()
		myFuncs.findExisting(defaultApps.terminal, defaultApps.terminalCommand)
	end, "T1 tap => find existing terminal"),
	tk({ modkey, ctrl, altkey }, "1", function()
		myFuncs.openNew(defaultApps.terminalCommand)
	end, "T1 hold => open new terminal"),
	tk({ modkey, ctrl, shft }, "1", function()
		myFuncs.viewWorkspace(1)
	end, "T1 mod tap => switch to tag 1"),
	tk({ modkey, ctrl, altkey, shft }, "1", function()
		myFuncs.moveWindowToWorkspace(1)
	end, "T1 mod hold => move focused window to tag 1"),

	-- Key 2
	tk({ modkey, ctrl }, "2", function()
		myFuncs.findExisting(defaultApps.browser, defaultApps.browserCommand)
	end, "T2 tap => find existing browser"),
	tk({ modkey, ctrl, altkey }, "2", function()
		myFuncs.openNew(defaultApps.browserCommand)
	end, "T2 hold => open new browser"),
	tk({ modkey, ctrl, shft }, "2", function()
		myFuncs.viewWorkspace(2)
	end, "T2 mod tap => viewWorkspace(2)"),
	tk({ modkey, ctrl, altkey, shft }, "2", function()
		myFuncs.moveWindowToWorkspace(2)
	end, "T2 mod hold => moveWindowToWorkspace(2)"),

	-- Key 3
	tk({ modkey, ctrl }, "3", function()
		myFuncs.findExisting(defaultApps.editor, defaultApps.editorCommand)
	end, "T3 tap => find existing editor"),
	tk({ modkey, ctrl, altkey }, "3", function()
		myFuncs.openNew(defaultApps.editorCommand)
	end, "T3 hold => open new editor"),
	tk({ modkey, ctrl, shft }, "3", function()
		myFuncs.viewWorkspace(3)
	end, "T3 mod tap => viewWorkspace(3)"),
	tk({ modkey, ctrl, altkey, shft }, "3", function()
		myFuncs.moveWindowToWorkspace(3)
	end, "T3 mod hold => moveWindowToWorkspace(3)"),

	-- Key 4
	tk({ modkey, ctrl }, "4", function()
		myFuncs.findExisting(defaultApps.fileManager, defaultApps.fileManagerCommand)
	end, "T4 tap => find existing file manager"),
	tk({ modkey, ctrl, altkey }, "4", function()
		myFuncs.openNew(defaultApps.fileManagerCommand)
	end, "T4 hold => open new file manager"),
	tk({ modkey, ctrl, shft }, "4", function()
		myFuncs.viewWorkspace(4)
	end, "T4 mod tap => viewWorkspace(4)"),
	tk({ modkey, ctrl, altkey, shft }, "4", function()
		myFuncs.moveWindowToWorkspace(4)
	end, "T4 mod hold => moveWindowToWorkspace(4)"),

	-- Key 5
	tk({ modkey, ctrl }, "5", function()
		myFuncs.openRofi()
	end, "T5 tap => launch rofi"),
	tk({ modkey, ctrl, altkey }, "5", function()
		myFuncs.lockScreen()
	end, "T5 hold => lock screen"),
	tk({ modkey, ctrl, shft }, "5", function()
		myFuncs.viewWorkspace(5)
	end, "T5 mod tap => viewWorkspace(5)"),
	tk({ modkey, ctrl, altkey, shft }, "5", function()
		myFuncs.moveWindowToWorkspace(5)
	end, "T5 mod hold => moveWindowToWorkspace(5)"),

	--------------------------------------------------
	-- Row 2: tab, q, w, e, r
	-- We'll assign some real actions, then default to notify
	--------------------------------------------------

	-- Key tab
	tk({ modkey, ctrl }, "Tab", function()
		myFuncs.addToInbox()
	end, "Tab tap => add to inbox"),
	tk({ modkey, ctrl, altkey }, "Tab", function()
		myFuncs.addToInbox()
	end, "Tab hold => focusRight"), -- example
	tk({ modkey, ctrl, shft }, "Tab", function()
		stack.clearStacks()
	end, "Tab mod tap => clear stacks"),
	tk({ modkey, ctrl, altkey, shft }, "Tab", function()
		myFuncs.moveWindowToWorkspace(6)
	end, "Tab mod hold => moveWindowToWorkspace(6)"),

	-- Key q
	tk({ modkey, ctrl }, "q", function()
		myFuncs.viewPopulatedTag("previous")
	end, "Q tap => previous populated tag"),
	tk({ modkey, ctrl, altkey }, "q", function()
		myFuncs.openBrowser("google-chrome")
	end, "Q hold => open chrome"),
	tk({ modkey, ctrl, shft }, "q", function()
		stack.cycleStack()
	end, "Q mod tap => cycle stack"),
	tk({ modkey, ctrl, altkey, shft }, "q", function()
		myFuncs.moveWindowToWorkspace(7)
	end, "Q mod hold => moveWindowToWorkspace(7)"),

	-- Key w
	tk({ modkey, ctrl }, "w", function()
		myFuncs.moveFocus("up")
	end, "W tap => move focus up"),
	tk({ modkey, ctrl, altkey }, "w", function()
		myFuncs.swapWindow("up")
	end, "W hold => swap window up"),
	tk({ modkey, ctrl, shft }, "w", function()
		stack.stackByDirection("up")
	end, "W mod tap => workspace(8)"),
	tk({ modkey, ctrl, altkey, shft }, "w", function()
		myFuncs.moveWindowToWorkspace(8)
	end, "W mod hold => moveWindowToWorkspace(8)"),

	-- Key e
	tk({ modkey, ctrl }, "e", function()
		myFuncs.viewPopulatedTag("next")
	end, "E tap => next populated tag"),
	tk({ modkey, ctrl, altkey }, "e", function()
		myFuncs.toggleFloating()
	end, "E hold => toggleFloating"),
	tk({ modkey, ctrl, shft }, "e", function()
		myFuncs.viewWorkspace(9)
	end, "E mod tap => workspace(9)"),
	tk({ modkey, ctrl, altkey, shft }, "e", function()
		myFuncs.moveWindowToWorkspace(9)
	end, "E mod hold => moveWindowToWorkspace(9)"),

	-- Key r
	tk({ modkey, ctrl }, "r", function()
		myFuncs.reloadAwesome()
	end, "R tap => reload awesome"),
	tk({ modkey, ctrl, altkey }, "r", function()
		myFuncs.showCheatsheet()
	end, "R hold => show cheatsheet"),
	tk({ modkey, ctrl, shft }, "r", function()
		myFuncs.viewWorkspace(10)
	end, "R mod tap => workspace(10)"),
	tk({ modkey, ctrl, altkey, shft }, "r", function()
		myFuncs.moveWindowToWorkspace(10)
	end, "R mod hold => moveWindowToWorkspace(10)"),

	--------------------------------------------------
	-- Row 3: caps, a, s, d, f
	-- We'll use naughty.notify placeholders here
	--------------------------------------------------

	-- Key caps (mapped to 6 for compatibility)
	tk({ modkey, ctrl }, "6", function()
		naughty.notify({ title = "T Caps", text = "tap pressed" })
	end, "Caps tap => notify"),
	tk({ modkey, ctrl, altkey }, "6", function()
		naughty.notify({ title = "T Caps", text = "tap+hold pressed" })
	end, "Caps hold => notify"),
	tk({ modkey, ctrl, shft }, "6", function()
		naughty.notify({ title = "T Caps", text = "mod tap pressed" })
	end, "Caps mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "6", function()
		naughty.notify({ title = "T Caps", text = "mod tap+hold" })
	end, "Caps mod hold => notify"),

	-- Key a
	tk({ modkey, ctrl }, "a", function()
		myFuncs.moveFocus("left")
	end, "A tap => move focus left"),
	tk({ modkey, ctrl, altkey }, "a", function()
		myFuncs.swapWindow("left")
	end, "A hold => swap window left"),
	tk({ modkey, ctrl, shft }, "a", function()
		naughty.notify({ title = "T a", text = "mod tap pressed" })
	end, "A mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "a", function()
		naughty.notify({ title = "T a", text = "mod tap+hold pressed" })
	end, "A mod hold => notify"),

	-- Key s
	tk({ modkey, ctrl }, "s", function()
		myFuncs.moveFocus("down")
	end, "S tap => move focus down"),
	tk({ modkey, ctrl, altkey }, "s", function()
		myFuncs.swapWindow("down")
	end, "S hold => swap window down"),
	tk({ modkey, ctrl, shft }, "s", function()
		naughty.notify({ title = "T s", text = "mod tap pressed" })
	end, "S mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "s", function()
		naughty.notify({ title = "T s", text = "mod tap+hold pressed" })
	end, "S mod hold => notify"),

	-- Key d
	tk({ modkey, ctrl }, "d", function()
		myFuncs.moveFocus("right")
	end, "D tap => move focus right"),
	tk({ modkey, ctrl, altkey }, "d", function()
		myFuncs.swapWindow("right")
	end, "D hold => swap window right"),
	tk({ modkey, ctrl, shft }, "d", function()
		naughty.notify({ title = "T d", text = "mod tap pressed" })
	end, "D mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "d", function()
		naughty.notify({ title = "T d", text = "mod tap+hold pressed" })
	end, "D mod hold => notify"),

	-- Key f
	tk({ modkey, ctrl }, "f", function()
		naughty.notify({ title = "T f", text = "tap pressed" })
	end, "F tap => notify"),
	tk({ modkey, ctrl, altkey }, "f", function()
		naughty.notify({ title = "T f", text = "tap+hold pressed" })
	end, "F hold => notify"),
	tk({ modkey, ctrl, shft }, "f", function()
		naughty.notify({ title = "T f", text = "mod tap pressed" })
	end, "F mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "f", function()
		naughty.notify({ title = "T f", text = "mod tap+hold pressed" })
	end, "F mod hold => notify"),

	--------------------------------------------------
	-- Row 4: shift, z, x, c, space
	-- We'll do placeholders with naughty.notify here as well
	--------------------------------------------------

	-- Key shift (mapped to 7 for compatibility)
	tk({ modkey, ctrl }, "7", function()
		naughty.notify({ title = "T shift", text = "tap pressed" })
	end, "Shift tap => notify"),
	tk({ modkey, ctrl, altkey }, "7", function()
		naughty.notify({ title = "T shift", text = "tap+hold pressed" })
	end, "Shift hold => notify"),
	tk({ modkey, ctrl, shft }, "7", function()
		naughty.notify({ title = "T shift", text = "mod tap pressed" })
	end, "Shift mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "7", function()
		naughty.notify({ title = "T shift", text = "mod tap+hold pressed" })
	end, "Shift mod hold => notify"),

	-- Key z
	tk({ modkey, ctrl }, "z", function()
		naughty.notify({ title = "T z", text = "tap pressed" })
	end, "Z tap => notify"),
	tk({ modkey, ctrl, altkey }, "z", function()
		naughty.notify({ title = "T z", text = "tap+hold pressed" })
	end, "Z hold => notify"),
	tk({ modkey, ctrl, shft }, "z", function()
		naughty.notify({ title = "T z", text = "mod tap pressed" })
	end, "Z mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "z", function()
		naughty.notify({ title = "T z", text = "mod tap+hold pressed" })
	end, "Z mod hold => notify"),

	-- Key x
	tk({ modkey, ctrl }, "x", function()
		naughty.notify({ title = "T x", text = "tap pressed" })
	end, "X tap => notify"),
	tk({ modkey, ctrl, altkey }, "x", function()
		naughty.notify({ title = "T x", text = "tap+hold pressed" })
	end, "X hold => notify"),
	tk({ modkey, ctrl, shft }, "x", function()
		naughty.notify({ title = "T x", text = "mod tap pressed" })
	end, "X mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "x", function()
		naughty.notify({ title = "T x", text = "mod tap+hold pressed" })
	end, "X mod hold => notify"),

	-- Key c
	tk({ modkey, ctrl }, "c", function()
		myFuncs.bitwardenPasswordCLI()
	end, "C tap => bitwardenPasswordCLI"),
	tk({ modkey, ctrl, altkey }, "c", function()
		naughty.notify({ title = "T c", text = "tap+hold pressed" })
	end, "C hold => notify"),
	tk({ modkey, ctrl, shft }, "c", function()
		naughty.notify({ title = "T c", text = "mod tap pressed" })
	end, "C mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "c", function()
		naughty.notify({ title = "T c", text = "mod tap+hold pressed" })
	end, "C mod hold => notify"),

	-- Key space
	tk({ modkey, ctrl }, "space", function()
		myFuncs.addInboxTodo()
	end, "Tab tap => add to inbox"),
	tk({ modkey, ctrl, altkey }, "space", function()
		local function loadCodeWorkspace()
			myFuncs.loadWorkspaceConfiguration()
		end
		gears.timer.delayed_call(loadCodeWorkspace)
	end, "R hold => show cheatsheet"),
	tk({ modkey, ctrl, shft }, "space", function()
		naughty.notify({ title = "T space", text = "mod tap pressed" })
	end, "Space mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "space", function()
		naughty.notify({ title = "T space", text = "mod tap+hold pressed" })
	end, "Space mod hold => notify")
) -- end of globalkeys

return tartarus
