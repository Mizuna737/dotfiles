-- signals.lua
-- Receives D-Bus gesture signals from gestureControl.py and routes them
-- to registered Lua handlers.
--
-- To add a new gesture binding, call onFire / onUpdate / onEnd at the
-- bottom of this file. Signal names correspond to binding names in triggers.toml.
--
-- Handler signatures:
--   onFire(name,   function(hand) end)
--   onUpdate(name, function(hand, value) end)   value: normalised [0.0 – 1.0]
--   onEnd(name,    function(hand) end)
--   onProgress(name, function(hand, step, total) end)

local awful   = require("awful")
local gears   = require("gears")
local myFuncs = require("functions")
local stack   = require("stack")

local IFACE = "org.gesturecontrol.Engine"

-- ── Hysteresis helpers ────────────────────────────────────────────────────────
-- Shared by tag_cycle and stack_cycle.
-- snapIndex:       first-frame snap — immediately land on the natural slot.
-- hysteresisIndex: require overshooting past the next boundary by HYST before
--                  changing slots, preventing jitter at edges.

local HYST = 0.04

local function snapIndex(value, count)
	return math.max(1, math.min(count, math.floor(value * count) + 1))
end

local function hysteresisIndex(current, value, count)
	local lower = (current - 1) / count - HYST
	local upper =  current      / count + HYST
	if value < lower then return math.max(1, current - 1) end
	if value > upper then return math.min(count, current + 1) end
	return current
end

-- ── Dispatch tables ───────────────────────────────────────────────────────────

local firedHandlers = {}
local updateHandlers = {}
local endHandlers = {}
local progressHandlers = {}

local function onFire(name, fn)
	firedHandlers[name] = fn
end
local function onUpdate(name, fn)
	updateHandlers[name] = fn
end
local function onEnd(name, fn)
	endHandlers[name] = fn
end
local function onProgress(name, fn)
	progressHandlers[name] = fn
end

-- ── D-Bus intake ──────────────────────────────────────────────────────────────

dbus.add_match("session", "type='signal',interface='" .. IFACE .. "'")

dbus.connect_signal(IFACE, function(data, ...)
	local args = { ... }
	local member = data.member

	if member == "GestureFired" then
		local fn = firedHandlers[args[1]]
		if fn then
			fn(args[2])
		end
	elseif member == "ContinuousUpdate" then
		local fn = updateHandlers[args[1]]
		if fn then
			fn(args[2], args[3])
		end
	elseif member == "ContinuousEnd" then
		local fn = endHandlers[args[1]]
		if fn then
			fn(args[2])
		end
	elseif member == "SequenceProgress" then
		local fn = progressHandlers[args[1]]
		if fn then
			fn(args[2], args[3], args[4])
		end
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

-- Tag cycling — left FOUR, finger spread sweeps across tags 1–5.
local tagCycleTag = nil
local TAG_COUNT   = 5

onUpdate("tag_cycle", function(hand, value)
	if tagCycleTag == nil then
		tagCycleTag = snapIndex(value, TAG_COUNT)
		local s = awful.screen.focused()
		if s.tags[tagCycleTag] then s.tags[tagCycleTag]:view_only() end
		return
	end
	local newTag = hysteresisIndex(tagCycleTag, value, TAG_COUNT)
	if newTag ~= tagCycleTag then
		tagCycleTag = newTag
		local s = awful.screen.focused()
		if s.tags[tagCycleTag] then s.tags[tagCycleTag]:view_only() end
	end
end)

onEnd("tag_cycle", function(hand)
	tagCycleTag = nil  -- reset so next activation snaps cleanly
end)

-- Volume
onUpdate("set_volume", function(hand, value)
	myFuncs.volumeControl("set", myFuncs.roundToNearest(5, value * 200))
end)

-- Window stacking
onFire("stack_all", function() stack.stackAll() end)

local stackCycleIdx = nil

onUpdate("stack_cycle", function(hand, value)
	if stackCycleIdx == nil then
		stack.stackAll()
		local count = stack.stackFrameSize()
		if count < 2 then return end
		stackCycleIdx = snapIndex(value, count)
		stack.stackActivate(stackCycleIdx)
		return
	end
	local count = stack.stackFrameSize()
	if count < 2 then return end
	local newIdx = hysteresisIndex(stackCycleIdx, value, count)
	if newIdx ~= stackCycleIdx then
		stackCycleIdx = newIdx
		stack.stackActivate(stackCycleIdx)
	end
end)

onEnd("stack_cycle", function(hand)
	stackCycleIdx = nil
	stack.unstackAll()
end)
