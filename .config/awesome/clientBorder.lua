local wibox = require("wibox")
local gears = require("gears")
local awful = require("awful")
local beautiful = require("beautiful")

local M = {}
local borders = {}

local function makeFrameWidget()
  local widget = wibox.widget.base.make_widget()
  widget.color = "#000000"
  widget.thickness = 0
  widget.radius = 0
  function widget:fit(_, w, h) return w, h end
  function widget:draw(_, cr, w, h)
    local t = self.thickness
    if t <= 0 or w <= 0 or h <= 0 then return end
    local r = self.radius
    local innerR = math.max(0, r - t)
    cr:set_source(gears.color(self.color))
    cr:new_sub_path()
    cr:arc(w - r, r, r, -math.pi/2, 0)
    cr:arc(w - r, h - r, r, 0, math.pi/2)
    cr:arc(r, h - r, r, math.pi/2, math.pi)
    cr:arc(r, r, r, math.pi, 3*math.pi/2)
    cr:close_path()
    cr:new_sub_path()
    cr:arc_negative(t + innerR, t + innerR, innerR, math.pi, math.pi/2)
    cr:arc_negative(w - t - innerR, t + innerR, innerR, math.pi/2, 0)
    cr:arc_negative(w - t - innerR, h - t - innerR, innerR, 0, -math.pi/2)
    cr:arc_negative(t + innerR, h - t - innerR, innerR, -math.pi/2, -math.pi)
    cr:close_path()
    cr:set_fill_rule("EVEN_ODD")
    cr:fill()
  end
  return widget
end

local function visibleFor(c)
  return c.valid and c:isvisible() and not c.minimized and not c.fullscreen
end

local function place(c, b)
  if not visibleFor(c) or b.thickness <= 0 then
    if b.shown then b.frame.visible = false; b.shown = false end
    return
  end
  local g = c:geometry()
  local key = g.x .. "," .. g.y .. "," .. g.width .. "," .. g.height
  if b.placedKey ~= key then
    b.frame:geometry({ x = g.x, y = g.y, width = g.width, height = g.height })
    b.placedKey = key
  end
  if not b.shown then b.frame.visible = true; b.shown = true end
end

function M.attach(c)
  if borders[c] then return end
  local widget = makeFrameWidget()
  local frame = wibox({
    ontop = true,
    visible = false,
    type = "dock",
    input_passthrough = true,
    bg = "#00000000",
  })
  frame.widget = widget

  local b = {
    frame = frame,
    widget = widget,
    color = "#000000",
    thickness = 0,
    radius = beautiful.cornerRadius or 12,
    placedKey = nil,
    shown = false,
  }
  widget.radius = b.radius
  borders[c] = b

  local function refresh() M.refresh(c) end
  c:connect_signal("property::geometry", refresh)
  c:connect_signal("property::minimized", refresh)
  c:connect_signal("property::hidden", refresh)
  c:connect_signal("property::fullscreen", refresh)
  c:connect_signal("property::screen", refresh)
  c:connect_signal("unmanage", function() M.detach(c) end)
end

function M.detach(c)
  local b = borders[c]; if not b then return end
  b.frame.visible = false
  b.frame = nil
  borders[c] = nil
end

function M.update(c, width, color)
  local b = borders[c]; if not b then return end
  local changed = false
  if b.color ~= color then
    b.color = color
    b.widget.color = color
    changed = true
  end
  if b.thickness ~= width then
    b.thickness = width
    b.widget.thickness = width
    changed = true
  end
  if changed then
    b.widget:emit_signal("widget::redraw_needed")
  end
  place(c, b)
end

function M.refresh(c)
  local b = borders[c]; if not b then return end
  place(c, b)
end

function M.refreshAll()
  for c, _ in pairs(borders) do M.refresh(c) end
end

local function onTagChange()
  gears.timer.delayed_call(M.refreshAll)
end
awful.tag.attached_connect_signal(nil, "property::selected", onTagChange)

return M
