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
  Tartarus Key Assignments
  
  Columns:
    1) Key # (1–20)
    2) Default Assignment (physical label)
    3) Tap (short press)
    4) Tap+Hold (long press)
    5) Modified Tap (short press + T21 modifier)
    6) Modified Tap+Hold (long press + T21 modifier)
  
  | #  | Default | Tap               | Tap+Hold               | Mod Tap                 | Mod Tap+Hold                |
  |----|---------|-------------------|------------------------|-------------------------|-----------------------------|
  | 1  | 1       | Find Terminal     | Find Global/Open       | View Tag 1              | View Tag 1 (Exclusive)      |
  | 2  | 2       | Find Browser      | Find Global/Open       | View Tag 2              | View Tag 2 (Exclusive)      |
  | 3  | 3       | Find Editor       | Find Global/Open       | View Tag 3              | View Tag 3 (Exclusive)      |
  | 4  | 4       | Find File Browser | Find Global/Open       | View Tag 4              | View Tag 4 (Exclusive)      |
  | 5  | 5       | Find Comms        | Find Global/Open       | View Tag 5              | View Tag 5 (Exclusive)      |
  | 6  | tab     | Stack All On Tag  | Stack Related          | Temp Stack (Alt+Tab)    | Stack All Global            |
  | 7  | q       | Cycle Stack Left  | Cycle Layout Left      | Previous Populated Tag  | Previous Tag                |
  | 8  | w       | Unstack Current   |                        | Focus Up                | Swap Up                     |
  | 9  | e       | Cycle Stack Right | Cycle Layout Right     | Next Populated Tag      | Next Tag                    |
  | 10 | r       | Unstack All       | Show Cheatsheet        |                         |                             |
  | 11 | caps    |                   |                        |                         |                             |
  | 12 | a       |                   |                        | Focus Left              | Swap Left                   |
  | 13 | s       | Eisenhower        | Quick Notes            | Focus Down              | Swap Down                   |
  | 14 | d       |                   |                        | Focus Right             | Swap Right                  |
  | 15 | f       | Audio Sink        | VPN                    |                         |                             |
  | 16 | shift   |                   |                        |                         |                             |
  | 17 | z       |                   |                        |                         |                             |
  | 18 | x       |                   |                        |                         |                             |
  | 19 | c       |                   |                        |                         |                             |
  | 20 | space   | Capture Task      | File Tasks             |                         |                             |
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
		myFuncs.findExisting(defaultApps.terminal, defaultApps.terminalCommand, "all")
	end, "T1 hold => open new terminal"),
	tk({ modkey, ctrl, shft }, "1", function()
		myFuncs.viewWorkspace(1)
	end, "T1 mod tap => switch to tag 1"),
	tk({ modkey, ctrl, altkey, shft }, "1", function()
		myFuncs.viewWorkspaceExclusive(1)
	end, "T1 mod hold => view tag 1 exclusive"),

	-- Key 2
	tk({ modkey, ctrl }, "2", function()
		myFuncs.findExisting(defaultApps.browser, defaultApps.browserCommand)
	end, "T2 tap => find existing browser"),
	tk({ modkey, ctrl, altkey }, "2", function()
		myFuncs.findExisting(defaultApps.browser, defaultApps.browserCommand, "all")
	end, "T2 hold => open new browser"),
	tk({ modkey, ctrl, shft }, "2", function()
		myFuncs.viewWorkspace(2)
	end, "T2 mod tap => viewWorkspace(2)"),
	tk({ modkey, ctrl, altkey, shft }, "2", function()
		myFuncs.viewWorkspaceExclusive(2)
	end, "T2 mod hold => view tag 2 exclusive"),

	-- Key 3
	tk({ modkey, ctrl }, "3", function()
		myFuncs.findExisting(defaultApps.editor, defaultApps.editorCommand)
	end, "T3 tap => find existing editor"),
	tk({ modkey, ctrl, altkey }, "3", function()
		myFuncs.findExisting(defaultApps.editor, defaultApps.editorCommand, "all")
	end, "T3 hold => open new editor"),
	tk({ modkey, ctrl, shft }, "3", function()
		myFuncs.viewWorkspace(3)
	end, "T3 mod tap => viewWorkspace(3)"),
	tk({ modkey, ctrl, altkey, shft }, "3", function()
		myFuncs.viewWorkspaceExclusive(3)
	end, "T3 mod hold => view tag 3 exclusive"),

	-- Key 4
	tk({ modkey, ctrl }, "4", function()
		myFuncs.findExisting(defaultApps.fileManager, defaultApps.fileManagerCommand)
	end, "T4 tap => find existing file manager"),
	tk({ modkey, ctrl, altkey }, "4", function()
		myFuncs.findExisting(defaultApps.fileManager, defaultApps.fileManagerCommand, "all")
	end, "T4 hold => open new file manager"),
	tk({ modkey, ctrl, shft }, "4", function()
		myFuncs.viewWorkspace(4)
	end, "T4 mod tap => viewWorkspace(4)"),
	tk({ modkey, ctrl, altkey, shft }, "4", function()
		myFuncs.viewWorkspaceExclusive(4)
	end, "T4 mod hold => view tag 4 exclusive"),

	-- Key 5
	tk({ modkey, ctrl }, "5", function()
		myFuncs.findComms()
	end, "T5 tap => find comms (current tag)"),
	tk({ modkey, ctrl, altkey }, "5", function()
		myFuncs.findComms("all")
	end, "T5 hold => find comms (global)"),
	tk({ modkey, ctrl, shft }, "5", function()
		myFuncs.viewWorkspace(5)
	end, "T5 mod tap => viewWorkspace(5)"),
	tk({ modkey, ctrl, altkey, shft }, "5", function()
		myFuncs.viewWorkspaceExclusive(5)
	end, "T5 mod hold => view tag 5 exclusive"),

	--------------------------------------------------
	-- Row 2: tab, q, w, e, r
	-- We'll assign some real actions, then default to notify
	--------------------------------------------------

	-- Key tab
	tk({ modkey, ctrl }, "Tab", function()
		stack.stackAll()
	end, "Tab tap => stack all"),

	tk({ modkey, ctrl, altkey }, "Tab", function()
		stack.stackRelated()
	end, "Tab hold => stack related windows"),

	tk({ modkey, ctrl, shft }, "Tab", function()
		stack.tempStack()
	end, "Tab mod tap => temp stack"),

	tk({ modkey, ctrl, altkey, shft }, "Tab", function()
		stack.stackAllGlobal()
	end, "Tab mod hold => stack all global"),

	-- Key q
	tk({ modkey, ctrl }, "q", function()
		stack.cycleStackForward()
	end, "Q tap => cycle stack forward"),

	tk({ modkey, ctrl, altkey }, "q", function()
		myFuncs.prevLayoutForTag()
	end, "Q hold => cycle layout left"),

	tk({ modkey, ctrl, shft }, "q", function()
		myFuncs.viewPopulatedTag("previous")
	end, "Q mod tap => previous populated tag"),

	tk({ modkey, ctrl, altkey, shft }, "q", function()
		awful.tag.viewprev()
	end, "Q mod hold => previous tag"),

	-- Key w
	tk({ modkey, ctrl }, "w", function()
		stack.unstackCurrent()
	end, "W tap => unstack current"),

	tk({ modkey, ctrl, altkey }, "w", function()
		naughty.notify({ title = "T w", text = "tap+hold pressed" })
	end, "W hold => (unassigned)"),

	tk({ modkey, ctrl, shft }, "w", function()
		myFuncs.moveFocus("up")
	end, "W mod tap => focus up"),

	tk({ modkey, ctrl, altkey, shft }, "w", function()
		myFuncs.swapWindow("up")
	end, "W mod hold => swap up"),

	-- Key e
	tk({ modkey, ctrl }, "e", function()
		stack.cycleStackBackward()
	end, "E tap => cycle stack backward"),

	tk({ modkey, ctrl, altkey }, "e", function()
		myFuncs.nextLayoutForTag()
	end, "E hold => cycle layout right"),

	tk({ modkey, ctrl, shft }, "e", function()
		myFuncs.viewPopulatedTag("next")
	end, "E mod tap => next populated tag"),

	tk({ modkey, ctrl, altkey, shft }, "e", function()
		awful.tag.viewnext()
	end, "E mod hold => next tag"),

	-- Key r
	tk({ modkey, ctrl }, "r", function()
		stack.unstackAll()
	end, "R tap => unstack all"),

	tk({ modkey, ctrl, altkey }, "r", function()
		myFuncs.showCheatsheet()
	end, "R hold => show cheatsheet"),

	tk({ modkey, ctrl, shft }, "r", function()
		naughty.notify({ title = "T r", text = "mod tap pressed" })
	end, "R mod tap => (unassigned)"),

	tk({ modkey, ctrl, altkey, shft }, "r", function()
		naughty.notify({ title = "T r", text = "mod tap+hold pressed" })
	end, "R mod hold => (unassigned)"),

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
		naughty.notify({ title = "T a", text = "tap pressed" })
	end, "A tap => (unassigned)"),
	tk({ modkey, ctrl, altkey }, "a", function()
		naughty.notify({ title = "T a", text = "tap+hold pressed" })
	end, "A hold => (unassigned)"),
	tk({ modkey, ctrl, shft }, "a", function()
		myFuncs.moveFocus("left")
	end, "A mod tap => focus left"),
	tk({ modkey, ctrl, altkey, shft }, "a", function()
		myFuncs.swapWindow("left")
	end, "A mod hold => swap left"),

	-- Key s
	tk({ modkey, ctrl }, "s", function()
		myFuncs.toggleEisenhower()
	end, "S tap => eisenhower matrix"),
	tk({ modkey, ctrl, altkey }, "s", function()
		myFuncs.toggleQuickNotes()
	end, "S hold => quick notes"),
	tk({ modkey, ctrl, shft }, "s", function()
		myFuncs.moveFocus("down")
	end, "S mod tap => focus down"),
	tk({ modkey, ctrl, altkey, shft }, "s", function()
		myFuncs.swapWindow("down")
	end, "S mod hold => swap down"),

	-- Key d
	tk({ modkey, ctrl }, "d", function()
		naughty.notify({ title = "T d", text = "tap pressed" })
	end, "D tap => (unassigned)"),
	tk({ modkey, ctrl, altkey }, "d", function()
		naughty.notify({ title = "T d", text = "tap+hold pressed" })
	end, "D hold => (unassigned)"),
	tk({ modkey, ctrl, shft }, "d", function()
		myFuncs.moveFocus("right")
	end, "D mod tap => focus right"),
	tk({ modkey, ctrl, altkey, shft }, "d", function()
		myFuncs.swapWindow("right")
	end, "D mod hold => swap right"),

	-- Key f
	tk({ modkey, ctrl }, "f", function()
		myFuncs.cycleSink()
	end, "F tap => cycle audio sink"),
	tk({ modkey, ctrl, altkey }, "f", function()
		myFuncs.toggleVPN()
	end, "F hold => toggle VPN"),
	tk({ modkey, ctrl, shft }, "f", function()
		naughty.notify({ title = "T f", text = "mod tap pressed" })
	end, "F mod tap => (unassigned)"),
	tk({ modkey, ctrl, altkey, shft }, "f", function()
		naughty.notify({ title = "T f", text = "mod tap+hold pressed" })
	end, "F mod hold => (unassigned)"),

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
	end, "Space tap => add to inbox"),
	tk({ modkey, ctrl, altkey }, "space", function()
		myFuncs.fileTasks()
	end, "Space hold => File Tasks"),
	tk({ modkey, ctrl, shft }, "space", function()
		naughty.notify({ title = "T space", text = "mod tap pressed" })
	end, "Space mod tap => notify"),
	tk({ modkey, ctrl, altkey, shft }, "space", function()
		naughty.notify({ title = "T space", text = "mod tap+hold pressed" })
	end, "Space mod hold => notify")
) -- end of globalkeys

return tartarus
