-- cycleSelector.lua
-- Generic popup overlay that displays a list of items with one row
-- highlighted. Used by windowCycle and tagCycle for gesture-driven selection.

local wibox     = require("wibox")
local awful     = require("awful")
local beautiful = require("beautiful")

local WIDTH      = 420
local ROW_H      = 34
local PAD        = 8
local FONT       = beautiful.font or "monospace 11"

local BG_NORMAL  = beautiful.bg_normal        or "#1e1e2e"
local BG_ACTIVE  = beautiful.taglist_bg_focus or "#5294e2"
local FG_NORMAL  = beautiful.fg_normal        or "#cdd6f4"
local FG_ACTIVE  = beautiful.taglist_fg_focus or "#ffffff"
local BORDER     = beautiful.border_focus     or "#5294e2"

local _popup   = nil
local _items   = {}
local _idx     = 1
local _getTitle = nil

local function makeRow(item, active)
    local title = _getTitle(item, #_items, active)
    return wibox.widget {
        {
            {
                markup = active
                    and ("<b>" .. title .. "</b>")
                    or  title,
                font   = FONT,
                widget = wibox.widget.textbox,
            },
            left = PAD * 2, right = PAD * 2,
            top = math.floor(PAD / 2), bottom = math.floor(PAD / 2),
            widget = wibox.container.margin,
        },
        bg            = active and BG_ACTIVE or BG_NORMAL,
        fg            = active and FG_ACTIVE or FG_NORMAL,
        forced_height = ROW_H,
        widget        = wibox.container.background,
    }
end

local function buildWidget()
    local layout = wibox.layout.fixed.vertical()
    for i, item in ipairs(_items) do
        layout:add(makeRow(item, i == _idx))
    end
    return wibox.widget {
        layout,
        top = PAD, bottom = PAD,
        widget = wibox.container.margin,
    }
end

local function reposition(s, h)
    local x = math.floor((s.geometry.width  - WIDTH) / 2) + s.geometry.x
    local y = math.floor((s.geometry.height - h) / 2) + s.geometry.y
    return x, y
end

local M = {}

function M.show(items, activeIdx, getTitle)
    if not items or #items == 0 then return end
    _items   = items
    _idx     = activeIdx or 1
    _getTitle = getTitle

    local s = awful.screen.focused()
    local h = #_items * ROW_H + PAD * 2
    local x, y = reposition(s, h)

    if _popup then
        _popup.widget = buildWidget()
        _popup.height = h
        _popup.x = x
        _popup.y = y
    else
        _popup = wibox {
            x            = x,
            y            = y,
            width        = WIDTH,
            height       = h,
            visible      = true,
            ontop        = true,
            bg           = BG_NORMAL,
            border_width = 1,
            border_color = BORDER,
            widget       = buildWidget(),
        }
    end
end

function M.move(delta)
    if #_items == 0 then return _idx end
    _idx = ((_idx - 1 + delta) % #_items) + 1
    if _popup then _popup.widget = buildWidget() end
    return _idx
end

function M.hide()
    if _popup then
        _popup.visible = false
        _popup = nil
    end
    _items = {}
    _idx   = 1
    _getTitle = nil
end

return M
