-- signals.lua
-- Receives D-Bus gesture signals from gestureControl.py and routes them
-- to registered Lua handlers.
--
-- To add a new gesture binding, call onFire / onUpdate / onEnd at the
-- bottom of this file. Signal names correspond to binding names in triggers.toml.
--
-- Handler signatures:
--   onFire(name,   function(hand) end)
--   onUpdate(name, function(hand, value) end)   value: slot index (1..N) if RegisterSlots called, else [0.0 – 1.0]
--   onStart(name,  function(hand) end)
--   onEnd(name,    function(hand) end)
--   onProgress(name, function(hand, step, total) end)

local awful   = require("awful")
local gears   = require("gears")
local myFuncs     = require("functions")
local stack       = require("stack")
local windowCycle = require("windowCycle")

local IFACE     = "org.gesturecontrol.Engine"
local DBUS_NAME = "org.gesturecontrol"
local DBUS_PATH = "/org/gesturecontrol"

-- ── Dispatch tables ───────────────────────────────────────────────────────────

local firedHandlers    = {}
local startHandlers    = {}
local updateHandlers   = {}
local endHandlers      = {}
local progressHandlers = {}

local function onFire(name, fn)     firedHandlers[name]    = fn end
local function onStart(name, fn)    startHandlers[name]    = fn end
local function onUpdate(name, fn)   updateHandlers[name]   = fn end
local function onEnd(name, fn)      endHandlers[name]      = fn end
local function onProgress(name, fn) progressHandlers[name] = fn end

-- ── Slot registration ─────────────────────────────────────────────────────────
-- Call registerSlots(name, slots) to tell gestureControl.py to map the raw
-- [0,1] continuous value for `name` to discrete 1..slots indices before
-- emitting ContinuousUpdate.  Hysteresis deadzone is read from the binding's
-- triggers.toml config.  Any subscriber (not just Lua) can call RegisterSlots
-- via D-Bus directly.

local function registerSlots(name, slots)
	awful.spawn(string.format(
		"dbus-send --session --type=method_call --dest=%s %s %s.RegisterSlots" ..
		" string:%s int32:%d",
		DBUS_NAME, DBUS_PATH, IFACE, name, slots
	))
end

-- ── D-Bus intake ──────────────────────────────────────────────────────────────

dbus.add_match("session", "type='signal',interface='" .. IFACE .. "'")

dbus.connect_signal(IFACE, function(data, ...)
	local args   = { ... }
	local member = data.member

	if member == "GestureFired" then
		local fn = firedHandlers[args[1]]
		if fn then fn(args[2]) end
	elseif member == "ContinuousStart" then
		local fn = startHandlers[args[1]]
		if fn then fn(args[2]) end
	elseif member == "ContinuousUpdate" then
		local fn = updateHandlers[args[1]]
		if fn then fn(args[2], args[3]) end
	elseif member == "ContinuousEnd" then
		local fn = endHandlers[args[1]]
		if fn then fn(args[2]) end
	elseif member == "SequenceProgress" then
		local fn = progressHandlers[args[1]]
		if fn then fn(args[2], args[3], args[4]) end
	end
end)

-- ── Tag focus signal ─────────────────────────────────────────────────────────
-- When tag focus changes, focus the master window and center the mouse.
screen.connect_signal("tag::history::update", function(s)
	local t = s.selected_tag
	if not t then return end
	myFuncs.focusMaster()
end)

-- ── Gesture bindings ──────────────────────────────────────────────────────────

-- Tag switching — discrete poses
onFire("tag_1", function() awful.screen.focused().tags[1]:view_only() end)
onFire("tag_2", function() awful.screen.focused().tags[2]:view_only() end)
onFire("tag_3", function() awful.screen.focused().tags[3]:view_only() end)
onFire("tag_4", function() awful.screen.focused().tags[4]:view_only() end)
onFire("prev_tag", function() awful.tag.viewprev() end)
onFire("next_tag", function() awful.tag.viewnext() end)

-- Tag cycling — left THREE, pinch distance sweeps across tags 1–5.
-- Re-register slots on every activation so the engine always has fresh
-- slot config (mirrors stack_cycle; avoids startup race with awful.spawn).
onStart("tag_cycle", function(hand)
	registerSlots("tag_cycle", 5)
end)

onUpdate("tag_cycle", function(hand, value)
	local tag = awful.screen.focused().tags[math.floor(value + 0.5)]
	if tag then tag:view_only() end
end)

-- Volume
onUpdate("set_volume", function(hand, value)
	myFuncs.volumeControl("set", myFuncs.roundToNearest(5, value * 200))
end)

-- Window stacking
onFire("stack_all", function() stack.stackAll() end)

-- window_cycle: sweep right THREE across tiling clients on current tag;
-- releases promotes the selected client to master.
onStart("window_cycle", function(hand)
	local count = windowCycle.start()
	if count >= 2 then
		registerSlots("window_cycle", count)
	end
end)

onUpdate("window_cycle", function(hand, value)
	windowCycle.activate(math.floor(value))
end)

onEnd("window_cycle", function(hand)
	windowCycle.commit()
end)

