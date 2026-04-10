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

local myFuncs = require("functions")
local stack   = require("stack")

local IFACE = "org.gesturecontrol.Engine"

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

-- ── Gesture bindings ──────────────────────────────────────────────────────────

onUpdate("set_volume", function(hand, value)
	myFuncs.volumeControl("set", myFuncs.roundToNearest(5, value * 200))
end)

local stackCycleActive = false

onUpdate("stack_cycle", function(hand, value)
	if not stackCycleActive then
		stackCycleActive = true
		stack.stackAll()
	end
	stack.stackCycleToIndex(value)
end)

onEnd("stack_cycle", function(hand)
	stackCycleActive = false
	stack.unstackAll()
end)
