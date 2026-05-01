local gears = require("gears")

local M = {}
M.cyclePeriod = 2.0

local tickRate = 0.05
local pulsePhase = 0.0
local subscribers = {}
local pulseTimer = nil

local function hexToRgb(hex)
	hex = hex:gsub("#", "")
	return tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16)
end

local function lerpColor(a, b, t)
	local ar, ag, ab = hexToRgb(a)
	local br, bg, bb = hexToRgb(b)
	return string.format(
		"#%02x%02x%02x",
		math.floor(ar + (br - ar) * t + 0.5),
		math.floor(ag + (bg - ag) * t + 0.5),
		math.floor(ab + (bb - ab) * t + 0.5)
	)
end

function M.dim(hex, factor)
	local r, g, b = hexToRgb(hex)
	return string.format(
		"#%02x%02x%02x",
		math.floor(r * factor + 0.5),
		math.floor(g * factor + 0.5),
		math.floor(b * factor + 0.5)
	)
end

function M.blend(bright, dim)
	local t = (math.sin(math.pi * 2 * pulsePhase / M.cyclePeriod) + 1) / 2
	return lerpColor(dim, bright, t)
end

function M.blendNumber(high, low)
	local t = (math.sin(math.pi * 2 * pulsePhase / M.cyclePeriod) + 1) / 2
	return low + (high - low) * t
end

function M.subscribe(fn)
	subscribers[#subscribers + 1] = fn
end

function M.start()
	if pulseTimer then
		return
	end
	pulseTimer = gears.timer({
		timeout = tickRate,
		call_now = false,
		autostart = true,
		callback = function()
			pulsePhase = pulsePhase + tickRate
			if pulsePhase >= M.cyclePeriod then
				pulsePhase = pulsePhase - M.cyclePeriod
			end
			for _, fn in ipairs(subscribers) do
				fn()
			end
		end,
	})
end

return M
