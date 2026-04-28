local awful = require("awful")
local gears = require("gears")

local M = {}
M.muted = false

local function queryMute(onChange)
	awful.spawn.easy_async("timeout 2 pactl get-source-mute @DEFAULT_SOURCE@", function(stdout)
		local muted = string.find(stdout, "Mute: yes", 1, true) ~= nil
		if onChange then
			onChange(muted)
		end
	end)
end

local function startSubscribe()
	awful.spawn.with_line_callback("pactl subscribe", {
		stdout = function(line)
			if string.find(line, "source", 1, true) or string.find(line, "server", 1, true) then
				queryMute(function(muted)
					if muted ~= M.muted then
						M.muted = muted
						awesome.emit_signal("micMuteChanged", M.muted)
					end
				end)
			end
		end,
		exit = function()
			-- re-spawn after 2s if subscribe dies
			gears.timer.start_new(2, function()
				startSubscribe()
				return false
			end)
		end,
	})
end

function M.start()
	queryMute(function(muted)
		M.muted = muted
	end)
	startSubscribe()
end

return M
