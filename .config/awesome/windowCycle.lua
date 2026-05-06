-- windowCycle.lua
-- Cycles through tiling clients on the current tag via gesture or keyboard.
-- Displays a cycleSelector overlay during selection.
-- On commit, promotes the selected client to master.

local awful         = require("awful")
local cycleSelector = require("cycleSelector")

local M = {}

local _clients   = {}
local _focusedIdx = 1

local function getClientTitle(c)
    return c.class or c.name or "?"
end

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
    _focusedIdx = 1
    if #_clients >= 2 then
        cycleSelector.show(_clients, 1, getClientTitle)
    end
    return #_clients
end

-- Highlight and focus the client at 1-based slot index (reversed).
function M.activate(slotIdx)
    local idx = #_clients - slotIdx + 1
    local c = _clients[idx]
    if not c then return end
    cycleSelector.show(_clients, idx, getClientTitle)
    c:emit_signal("request::activate", "windowCycle", { raise = true })
end

-- Keyboard entry point: move selection by delta (+1/-1) in reversed order.
function M.step(delta)
    if #_clients == 0 then
        _clients = tagClients()
        cycleSelector.show(_clients, 1, getClientTitle)
    end
    _focusedIdx = _focusedIdx + delta
    if _focusedIdx < 1 then _focusedIdx = #_clients end
    if _focusedIdx > #_clients then _focusedIdx = 1 end
    local actualIdx = #_clients - _focusedIdx + 1
    local c = _clients[actualIdx]
    if c then c:emit_signal("request::activate", "windowCycle", { raise = true }) end
end

-- Promote selected client to master and close the selector.
function M.commit()
    local focused = client.focus
    if focused then
        awful.client.setmaster(focused)
    end
    cycleSelector.hide()
    _clients = {}
end

return M
