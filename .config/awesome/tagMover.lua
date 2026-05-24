local awful         = require("awful")
local gears         = require("gears")
local cycleSelector = require("cycleSelector")

local M = {}
local _grabber = nil
local _client  = nil
local _tags    = {}
local _idx     = 1

local function close()
    if _grabber then
        _grabber:stop()
        _grabber = nil
    end
    cycleSelector.hide()
    _client = nil
    _tags   = {}
    _idx    = 1
end

local function confirm()
    local c = _client
    local t = _tags[_idx]
    close()
    if not (c and c.valid and t) then return end
    c:move_to_tag(t)
    t:view_only()
    gears.timer.delayed_call(function()
        if c.valid then
            client.focus = c
            c:raise()
        end
    end)
end

function M.show()
    local c = client.focus
    if not c then return end
    _client = c

    local s = awful.screen.focused()
    _tags   = s.tags
    if #_tags == 0 then return end

    _idx = 1
    for i, t in ipairs(_tags) do
        if t == s.selected_tag then _idx = i; break end
    end

    cycleSelector.show(_tags, _idx, function(t)
        return t.name
    end)

    _grabber = awful.keygrabber({
        autostart = true,
        keypressed_callback = function(self, mod, key)
            if key == "j" or key == "Down" then
                _idx = cycleSelector.move(1)
            elseif key == "k" or key == "Up" then
                _idx = cycleSelector.move(-1)
            elseif key == "Return" then
                confirm()
            elseif key == "Escape" or key == "q" then
                close()
            end
        end,
    })
end

return M
