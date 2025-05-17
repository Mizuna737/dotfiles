-- stack.lua
local awful = require("awful")
local gears = require("gears")

local M = {}

-- baseStacks[baseWindow] = { list of stacked floating windows }
local baseStacks = setmetatable({}, { __mode = "k" })

-- Move handler
local function onBaseMove(base)
    local stack = baseStacks[base]
    if not stack then return end
    local g = base:geometry()
    for _, st in ipairs(stack) do
        if st.valid then
            st:geometry({ x=g.x, y=g.y, width=g.width, height=g.height })
        end
    end
end

local function bindBaseMovement(base)
    base:disconnect_signal("property::geometry", onBaseMove(base))
    base._stackMoveHandler = function(c) onBaseMove(c) end
    base:connect_signal("property::geometry", base._stackMoveHandler)
end

-- 1) Create or extend a stack by adding newClient on top of base
function M.stackWindow(base, newClient)
    if not baseStacks[base] then
        baseStacks[base] = {}
    end

    newClient.floating = true
    local g = base:geometry()
    newClient:geometry({ x=g.x, y=g.y, width=g.width, height=g.height })
    table.insert(baseStacks[base], newClient)
    bindBaseMovement(base)
end

-- 2) cycleStack for a given base
function M.cycleStack(base)
    local stack = baseStacks[base]
    if not stack or #stack == 0 then return end

    -- build combined list
    local combined = { base }
    for _, st in ipairs(stack) do
        table.insert(combined, st)
    end

    local fc = client.focus
    local idx = 1
    for i, c in ipairs(combined) do
        if c == fc then idx = i; break end
    end

    local newIdx = idx + 1
    if newIdx > #combined then
        newIdx = 1
    end

    local target = combined[newIdx]
    client.focus = target
    target:raise()
end

-- 3) findBaseFor window
function M.findBaseFor(c)
    if baseStacks[c] then
        return c
    end
    for b, list in pairs(baseStacks) do
        for _, st in ipairs(list) do
            if st == c then
                return b
            end
        end
    end
    return nil
end

-- 4) stackByDirection
function M.stackByDirection(direction)
    local c = client.focus
    if not c then return end
    local t = c.screen.selected_tag
    if not t then return end

    local cl = t:clients()
    if #cl < 2 then return end

    if direction == "left" or direction == "right" then
        table.sort(cl, function(a,b) return a:geometry().x < b:geometry().x end)
    else
        table.sort(cl, function(a,b) return a:geometry().y < b:geometry().y end)
    end

    local idx
    for i, w in ipairs(cl) do
        if w == c then idx = i; break end
    end
    if not idx then return end

    local step = (direction == "left" or direction == "up") and -1 or 1
    local newIdx = idx + step
    -- clamp or wrap
    if newIdx < 1 then newIdx = #cl
    elseif newIdx > #cl then newIdx = 1
    end

    local base = cl[newIdx]
    if base == c then return end

    M.stackWindow(base, c)
end

-- 5) override swap if user is focusing a stacked window
function M.swapOrRedirect(direction)
    local c = client.focus
    local base = M.findBaseFor(c)
    if base and base ~= c then
        -- swap base instead
        awful.client.swap.bydirection(direction, base)
    else
        -- normal swap
        awful.client.swap.bydirection(direction, c)
    end
end

return M
