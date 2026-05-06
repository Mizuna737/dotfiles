-- tagCycle.lua
-- Cycles through tags on the current screen via gesture.
-- Displays a cycleSelector popup during selection.
-- On commit, views the selected tag.

local awful         = require("awful")
local cycleSelector = require("cycleSelector")

local M = {}

local _tags = {}
local _idx  = 1

local function getTagName(tag, idx)
    return tag and (tag.name or ("Tag " .. tostring(idx))) or ("Tag " .. tostring(idx))
end

-- Gesture entry point: snapshot available tags and open the selector.
-- Returns tag count so the caller can register the right slot count.
function M.start()
    local screen = awful.screen.focused()
    _tags = screen and screen.tags or {}
    _idx  = 1
    local count = #_tags
    if count >= 2 then
        cycleSelector.show(_tags, 1, getTagName)
    end
    return count
end

-- Highlight and focus the tag at 1-based slot index.
function M.activate(slotIdx)
    _idx = #_tags - slotIdx + 1
    local tag = _tags[_idx]
    if not tag then return end
    cycleSelector.show(_tags, _idx, getTagName)
    tag:emit_signal("request::activate", "tagCycle", { view_only = true })
end

-- View the selected tag and close the selector.
function M.commit()
    local tag = _tags[_idx]
    if tag then
        tag:view_only()
    end
    cycleSelector.hide()
    _tags = {}
end

return M
