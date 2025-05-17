-- powerarrow theme.lua
-- Updated to use Ayu Mirage colors (only colors edited, sizes/spacings unchanged)

local gears = require("gears")
local lain = require("lain")
local awful = require("awful")
local wibox = require("wibox")
local dpi = require("beautiful.xresources").apply_dpi
local naughty = require("naughty")
local bar = require("bar") -- Adjust path if needed

local math, string, os = math, string, os

local theme = {}
theme.dir = os.getenv("HOME") .. "/.config/awesome/themes/powerarrow"
theme.wallpaper = theme.dir .. "/wall.png"
theme.font = "Terminus 9"

-- Ayu Mirage color definitions
-- Using values from the provided Ayu Mirage palette:
-- Background: '#1F2430'
-- Foreground: '#CBCCC6'
-- Accent colors (selected as needed):
--   Accent/Focus: '#5CCFE6'
--   Urgent: '#F28779'
--   Secondary / less prominent: '#5C6773'
--   A warm accent: '#FFA759'
theme.bg_normal = "#1F2430"
theme.fg_normal = "#CBCCC6"
theme.bg_focus = "#1F2430" -- Using same background; focus color will be applied on text
theme.fg_focus = "#5CCFE6"
theme.bg_urgent = "#1F2430"
theme.fg_urgent = "#FFA759"

theme.taglist_fg_focus = "#5CCFE6"
theme.tasklist_bg_focus = "#1F2430"
theme.tasklist_fg_focus = "#5CCFE6"

theme.border_width = dpi(2)
theme.border_normal = "#5C6773"
theme.border_focus = "#5CCFE6"
theme.border_marked = "#FFA759"

theme.titlebar_bg_focus = "#1F2430"
theme.titlebar_bg_normal = "#1F2430"
theme.titlebar_fg_focus = "#5CCFE6"

theme.menu_height = dpi(16)
theme.menu_width = dpi(140)
theme.menu_submenu_icon = theme.dir .. "/icons/submenu.png"
theme.awesome_icon = theme.dir .. "/icons/awesome.png"
theme.taglist_squares_sel = theme.dir .. "/icons/square_sel.png"
theme.taglist_squares_unsel = theme.dir .. "/icons/square_unsel.png"

-- Layout icons
theme.layout_tile = theme.dir .. "/icons/tile.png"
theme.layout_tileleft = theme.dir .. "/icons/tileleft.png"
theme.layout_tilebottom = theme.dir .. "/icons/tilebottom.png"
theme.layout_tiletop = theme.dir .. "/icons/tiletop.png"
theme.layout_fairv = theme.dir .. "/icons/fairv.png"
theme.layout_fairh = theme.dir .. "/icons/fairh.png"
theme.layout_spiral = theme.dir .. "/icons/spiral.png"
theme.layout_dwindle = theme.dir .. "/icons/dwindle.png"
theme.layout_max = theme.dir .. "/icons/max.png"
theme.layout_fullscreen = theme.dir .. "/icons/fullscreen.png"
theme.layout_magnifier = theme.dir .. "/icons/magnifier.png"
theme.layout_floating = theme.dir .. "/icons/floating.png"

-- Example widget icons
theme.widget_ac = theme.dir .. "/icons/ac.png"
theme.widget_battery = theme.dir .. "/icons/battery.png"
theme.widget_battery_low = theme.dir .. "/icons/battery_low.png"
theme.widget_battery_empty = theme.dir .. "/icons/battery_empty.png"
theme.widget_brightness = theme.dir .. "/icons/brightness.png"
theme.widget_mem = theme.dir .. "/icons/mem.png"
theme.widget_cpu = theme.dir .. "/icons/cpu.png"
theme.widget_temp = theme.dir .. "/icons/temp.png"
theme.widget_net = theme.dir .. "/icons/net.png"
theme.widget_hdd = theme.dir .. "/icons/hdd.png"
theme.widget_music = theme.dir .. "/icons/note.png"
theme.widget_music_on = theme.dir .. "/icons/note_on.png"
theme.widget_music_pause = theme.dir .. "/icons/pause.png"
theme.widget_music_stop = theme.dir .. "/icons/stop.png"
theme.widget_vol = theme.dir .. "/icons/vol.png"
theme.widget_vol_low = theme.dir .. "/icons/vol_low.png"
theme.widget_vol_no = theme.dir .. "/icons/vol_no.png"
theme.widget_vol_mute = theme.dir .. "/icons/vol_mute.png"
theme.widget_mail = theme.dir .. "/icons/mail.png"
theme.widget_mail_on = theme.dir .. "/icons/mail_on.png"
theme.widget_task = theme.dir .. "/icons/task.png"
theme.widget_scissors = theme.dir .. "/icons/scissors.png"

theme.tasklist_plain_task_name = true
theme.tasklist_disable_icon = true
theme.useless_gap = 0

-- Titlebar icons
theme.titlebar_close_button_focus = theme.dir .. "/icons/titlebar/close_focus.png"
theme.titlebar_close_button_normal = theme.dir .. "/icons/titlebar/close_normal.png"
theme.titlebar_ontop_button_focus_active = theme.dir .. "/icons/titlebar/ontop_focus_active.png"
theme.titlebar_ontop_button_normal_active = theme.dir .. "/icons/titlebar/ontop_normal_active.png"
theme.titlebar_ontop_button_focus_inactive = theme.dir .. "/icons/titlebar/ontop_focus_inactive.png"
theme.titlebar_ontop_button_normal_inactive = theme.dir .. "/icons/titlebar/ontop_normal_inactive.png"
theme.titlebar_sticky_button_focus_active = theme.dir .. "/icons/titlebar/sticky_focus_active.png"
theme.titlebar_sticky_button_normal_active = theme.dir .. "/icons/titlebar/sticky_normal_active.png"
theme.titlebar_sticky_button_focus_inactive = theme.dir .. "/icons/titlebar/sticky_focus_inactive.png"
theme.titlebar_sticky_button_normal_inactive = theme.dir .. "/icons/titlebar/sticky_normal_inactive.png"
theme.titlebar_floating_button_focus_active = theme.dir .. "/icons/titlebar/floating_focus_active.png"
theme.titlebar_floating_button_normal_active = theme.dir .. "/icons/titlebar/floating_normal_active.png"
theme.titlebar_floating_button_focus_inactive = theme.dir .. "/icons/titlebar/floating_focus_inactive.png"
theme.titlebar_floating_button_normal_inactive = theme.dir .. "/icons/titlebar/floating_normal_inactive.png"
theme.titlebar_maximized_button_focus_active = theme.dir .. "/icons/titlebar/maximized_focus_active.png"
theme.titlebar_maximized_button_normal_active = theme.dir .. "/icons/titlebar/maximized_normal_active.png"
theme.titlebar_maximized_button_focus_inactive = theme.dir .. "/icons/titlebar/maximized_focus_inactive.png"
theme.titlebar_maximized_button_normal_inactive = theme.dir .. "/icons/titlebar/maximized_normal_inactive.png"

--------------------------------------------------------------------------------
-- Additional widgets & code from the original snippet
--------------------------------------------------------------------------------

local markup = lain.util.markup
local separators = lain.util.separators
local binclock = require("themes.powerarrow.binclock")({
	height = dpi(32),
	show_seconds = true,
	color_active = theme.fg_normal,
	color_inactive = theme.bg_focus,
})

-- naughty.notify({ title = "Powerarrow Theme", text = "theme.lua loaded" })

--------------------------------------------------------------------------------
-- For your wibar arrow separators
--------------------------------------------------------------------------------

local arrow = separators.arrow_left

function theme.powerline_rl(cr, width, height)
	local arrow_depth, offset = height / 2, 0

	if arrow_depth < 0 then
		width = width + 2 * arrow_depth
		offset = -arrow_depth
	end

	cr:move_to(offset + arrow_depth, 0)
	cr:line_to(offset + width, 0)
	cr:line_to(offset + width - arrow_depth, height / 2)
	cr:line_to(offset + width, height)
	cr:line_to(offset + arrow_depth, height)
	cr:line_to(offset, height / 2)
	cr:close_path()
end

return theme
