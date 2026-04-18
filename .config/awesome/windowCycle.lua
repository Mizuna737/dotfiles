-- windowCycle.lua
-- Cycles through tiling clients on the current tag via gesture or keyboard.
-- Displays a cycleSelector overlay during selection.
-- On commit, promotes the selected client to master.

local awful         = require("awful")
local cycleSelector = require("cycleSelector")

local M = {}

local _clients = {}

local function tagClients()
    local t = awful.screen.focused().selected_tag
    if not t then return {} end
    local result = {}
    for _, c in ipairs(t:clients()) do
        if not c.minimized and not c.floating then
            table.insert(result, c)
        end
    end
    table.sort(result, function(a, b)
        if a.x ~= b.x then return a.x < b.x end
        return a.y < b.y
    end)
    return result
end

-- Gesture entry point: snapshot clients and open the selector.
-- Returns client count so the caller can register the right slot count.
function M.start()
    _clients = tagClients()
    if #_clients >= 2 then
        cycleSelector.show(_clients, 1)
    end
    return #_clients
end

-- Highlight and focus the client at 1-based index.
function M.activate(idx)
    local c = _clients[idx]
    if not c then return end
    cycleSelector.show(_clients, idx)
    c:emit_signal("request::activate", "windowCycle", { raise = true })
end

-- Keyboard entry point: open selector and move highlight by delta (+1/-1).
function M.step(delta)
    if #_clients == 0 then
        _clients = tagClients()
        cycleSelector.show(_clients, 1)
    end
    local idx = cycleSelector.move(delta)
    local c   = _clients[idx]
    if c then c:emit_signal("request::activate", "windowCycle", { raise = true }) end
end

-- Promote focused client to master and close the selector.
function M.commit()
    local focused = client.focus
    if focused then
        awful.client.setmaster(focused)
    end
    cycleSelector.hide()
    _clients = {}
end

return M
