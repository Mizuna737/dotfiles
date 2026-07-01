--------------------------------
-- bar.lua
-- A single file that creates and manages the AwesomeWM wibar, including:
-- CPU, Mem, Temp, Net, Volume, Date/Time, Focused Class, Systray, arrow separators,
-- plus a fallback Taglist / Tasklist if desired.
--------------------------------

local gears = require("gears")
local awful = require("awful")
local wibox = require("wibox")
local beautiful = require("beautiful")
local lain = require("lain")
local dpi = require("beautiful.xresources").apply_dpi
local bar = {}

--------------------------------
-- Taglist / Tasklist Button Definitions
--------------------------------
bar.taglist_buttons = gears.table.join(
	awful.button({}, 1, function(t)
		t:view_only()
	end),
	awful.button({ "Mod4" }, 1, function(t)
		if client.focus then
			client.focus:move_to_tag(t)
		end
	end),
	awful.button({}, 3, awful.tag.viewtoggle),
	awful.button({ "Mod4" }, 3, function(t)
		if client.focus then
			client.focus:toggle_tag(t)
		end
	end),
	awful.button({}, 4, function(t)
		awful.tag.viewnext(t.screen)
	end),
	awful.button({}, 5, function(t)
		awful.tag.viewprev(t.screen)
	end)
)

bar.tasklist_buttons = gears.table.join(
	awful.button({}, 1, function(c)
		if c == client.focus then
			c.minimized = true
		else
			c:emit_signal("request::activate", "tasklist", { raise = true })
		end
	end),
	awful.button({}, 3, function()
		awful.menu.client_list({ theme = { width = 250 } })
	end),
	awful.button({}, 4, function()
		awful.client.focus.byidx(1)
	end),
	awful.button({}, 5, function()
		awful.client.focus.byidx(-1)
	end)
)

--------------------------------
-- 1) CPU Widget
--------------------------------
local cpuicon = wibox.widget.imagebox(beautiful.widget_cpu or "")
local cpu = lain.widget.cpu({
	settings = function()
		widget:set_markup(" " .. cpu_now.usage .. "% ")
	end,
})

--------------------------------
-- 2) Memory Widget
--------------------------------
local memicon = wibox.widget.imagebox(beautiful.widget_mem or "")
local mem = lain.widget.mem({
	settings = function()
		widget:set_markup(" " .. mem_now.used .. "GB")
	end,
})

--------------------------------
-- 3) Network Widget
--------------------------------
local neticon = wibox.widget.imagebox(beautiful.widget_net or "")
local net = lain.widget.net({
	settings = function()
		widget:set_markup(" " .. net_now.received .. " ↓↑ " .. net_now.sent .. " ")
	end,
})

--------------------------------
-- 4) Volume Widget
--------------------------------
--
local volume_bar = wibox.widget({
	max_value = 200,
	value = 50,
	forced_height = 10,
	forced_width = 50,
	color = beautiful.bg_normal,
	background_color = beautiful.bg_normal,
	widget = wibox.widget.progressbar,
})

local volume_text_container = wibox.widget({
	{
		id = "old_text",
		text = "50%",
		align = "center",
		valign = "center",
		opacity = 1,
		widget = wibox.widget.textbox,
	},
	{
		id = "new_text",
		text = "50%",
		align = "center",
		valign = "center",
		opacity = 0,
		widget = wibox.widget.textbox,
	},
	layout = wibox.layout.stack,
})

local volume_widget = wibox.widget({
	volume_bar,
	volume_text_container,
	layout = wibox.layout.stack,
})

local normal_width, normal_height = 50, 10
local enlarged_width, enlarged_height = 70, 15
local shrink_timer = nil

local function animate_widget_size(target_width, target_height)
	local step = 2
	local current_width = volume_bar.forced_width
	local current_height = volume_bar.forced_height

	local timer = gears.timer.start_new(0.05, function()
		if current_width < target_width then
			current_width = current_width + step
			if current_width > target_width then
				current_width = target_width
			end
		elseif current_width > target_width then
			current_width = current_width - step
			if current_width < target_width then
				current_width = target_width
			end
		end

		if current_height < target_height then
			current_height = current_height + step
			if current_height > target_height then
				current_height = target_height
			end
		elseif current_height > target_height then
			current_height = current_height - step
			if current_height < target_height then
				current_height = target_height
			end
		end

		volume_bar.forced_width = current_width
		volume_bar.forced_height = current_height

		if current_width == target_width and current_height == target_height then
			timer:stop()
		end
		return true
	end)
end

local function updateVolumeText(new_volume_text)
	local old_textbox = volume_text_container:get_children_by_id("old_text")[1]
	local new_textbox = volume_text_container:get_children_by_id("new_text")[1]

	-- Set the new text in the 'new_text' box and reset opacities
	new_textbox.text = new_volume_text
	new_textbox.opacity = 0
	old_textbox.opacity = 1

	-- Define the fade-in/out steps
	local fade_duration = 0.01 -- in seconds
	local steps = 100
	local step_interval = fade_duration / steps
	local fade_step = 1 / steps

	-- Create a timer to handle the fade effect
	gears.timer({
		timeout = step_interval,
		autostart = true,
		call_now = true,
		callback = function(t)
			-- Decrease opacity of the old text and increase for the new text
			old_textbox.opacity = old_textbox.opacity - fade_step
			new_textbox.opacity = new_textbox.opacity + fade_step

			-- Stop the timer when fully faded
			if old_textbox.opacity <= 0 then
				-- Swap texts: make new text the 'old' one for next update
				old_textbox.text = new_textbox.text
				old_textbox.opacity = 1
				new_textbox.opacity = 0
				t:stop()
			end
		end,
	})
end

local function updateVolumeWidget()
	local old_text = volume_text_container:get_children_by_id("old_text")[1]
	local new_text = volume_text_container:get_children_by_id("new_text")[1]

	old_text.font = "Terminus 14"
	new_text.font = "Terminus 14"

	if shrink_timer then
		shrink_timer:stop()
	end

	volume_bar.background_color = beautiful.bg_normal .. "33" -- unfilled color
	volume_bar.color = beautiful.border_focus -- filled color
	animate_widget_size(enlarged_width, enlarged_height)

	awful.spawn.easy_async_with_shell("pactl get-sink-volume @DEFAULT_SINK@", function(stdout)
		local volpct = stdout:match("(%d+)%%")
		if volpct then
			volume_bar.value = tonumber(volpct)
			updateVolumeText(volpct .. "%")
		end
	end)

	shrink_timer = gears.timer.start_new(1, function()
		volume_bar.background_color = beautiful.bg_normal -- unfilled color
		volume_bar.color = beautiful.bg_normal -- filled color
		animate_widget_size(normal_width, normal_height)
		new_text.font = "Terminus 10"
		old_text.font = "Terminus 10"
	end)
end

-- Expose a function we can call from keybinds if needed
bar.updateVolumeWidget = updateVolumeWidget

--------------------------------
-- Volume sync timer (background drift correction)
--------------------------------
gears.timer({
	timeout   = 5,
	autostart = true,
	call_now  = true,
	callback  = function()
		awful.spawn.easy_async_with_shell("pactl get-sink-volume @DEFAULT_SINK@", function(stdout)
			local volpct = stdout:match("(%d+)%%")
			if volpct then
				volume_bar.value = tonumber(volpct)
				updateVolumeText(volpct .. "%")
			end
		end)
	end,
})

--------------------------------
-- 5) Date/Time Widget
--------------------------------

local date_text = wibox.widget.textbox()
local time_text = wibox.widget.textbox()

local function formatDateTime()
	local date = os.date("%A, %B %e")
	local day = os.date("*t").day
	local suffix

	if day % 10 == 1 and day ~= 11 then
		suffix = "st"
	elseif day % 10 == 2 and day ~= 12 then
		suffix = "nd"
	elseif day % 10 == 3 and day ~= 13 then
		suffix = "rd"
	else
		suffix = "th"
	end

	date = date .. suffix
	local time = os.date("%I:%M %p")
	return date, time
end

local function updateDateTime()
	local d, t = formatDateTime()
	date_text:set_text(d)
	time_text:set_text(t)
end

gears.timer({
	timeout = 10,
	autostart = true,
	callback = updateDateTime,
})
updateDateTime()

local date_time_widget = wibox.widget({
	date_text,
	time_text,
	layout = wibox.layout.fixed.horizontal,
	spacing = 15,
})

--------------------------------
-- 6) Focused Window Class Widget
--------------------------------

local focused_window_class = wibox.widget({
	text = "Loading...",
	align = "center",
	valign = "center",
	font = "Terminus 14",
	widget = wibox.widget.textbox,
})

local function updateFocusedClass()
	local c = client.focus
	local classname
	if c and c.instance == "dashboard" then
		classname = "dashboard"
	else
		classname = c and c.class or "Unknown"
	end
	focused_window_class:set_text(classname)
end

client.connect_signal("focus", updateFocusedClass)
client.connect_signal("unfocus", updateFocusedClass)
updateFocusedClass()

--------------------------------
-- 7) Systray
--------------------------------

local systray = wibox.widget({
	widget = wibox.widget.systray,
	base_size = beautiful.systray_icon_spacing or 20,
	horizontal = true,
	background_color = beautiful.bg_normal,
})

--------------------------------
-- 8) workAssistant status widget
--------------------------------

local waSpinnerFrames = {"⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"}
local waSpinnerIdx = 1
local waState = "idle"

local waWidget = wibox.widget({
    widget = wibox.widget.textbox,
    font   = beautiful.font,
})

local function waFileExists(path)
    local f = io.open(path)
    if f then f:close(); return true end
    return false
end

local function waUpdateWidget()
    if waState == "recording" then
        waWidget:set_markup('<span color="' .. (beautiful.fg_urgent or "#FF5555") .. '"> ● REC </span>')
    elseif waState == "transcribing" then
        local frame = waSpinnerFrames[waSpinnerIdx]
        waWidget:set_markup('<span color="' .. (beautiful.fg_focus or "#FFB86C") .. '"> ' .. frame .. ' Transcribing </span>')
    elseif waState == "notes" then
        local frame = waSpinnerFrames[waSpinnerIdx]
        waWidget:set_markup('<span color="' .. (beautiful.fg_focus or "#8BE9FD") .. '"> ' .. frame .. ' Notes </span>')
    else
        waWidget:set_markup("")
    end
end

-- Spinner animation: only runs while active, stopped at idle
local waSpinnerTimer = gears.timer({
    timeout   = 0.15,
    autostart = false,
    callback  = function()
        waSpinnerIdx = (waSpinnerIdx % #waSpinnerFrames) + 1
        waUpdateWidget()
    end,
})

-- State polling: cheap file checks at a relaxed rate
gears.timer({
    timeout   = 2,
    autostart = true,
    call_now  = true,
    callback  = function()
        local newState
        if waFileExists("/tmp/workAssistant-record.pid") then
            newState = "recording"
        elseif waFileExists("/tmp/workAssistant-transcribe.lock") then
            newState = "transcribing"
        elseif waFileExists("/tmp/workAssistant-notes.lock") then
            newState = "notes"
        else
            newState = "idle"
        end
        if newState ~= waState then
            waState = newState
            waUpdateWidget()
            if waState == "idle" then
                waSpinnerTimer:stop()
            else
                waSpinnerTimer:start()
            end
        end
    end,
})

--------------------------------
-- bar.setupWibar
--------------------------------

function bar.setupWibar()
	-- If you want to set wallpaper on geometry changes:
	screen.connect_signal("property::geometry", function(s)
		if beautiful.wallpaper then
			local w = beautiful.wallpaper
			if type(w) == "function" then
				w = w(s)
			end
			gears.wallpaper.maximized(w, s, true)
		end
	end)

	-- Actually build the bar on each screen
	awful.screen.connect_for_each_screen(function(s)
		if s ~= screen.primary then
			return
		end -- skip dashboard screen
		-- Taglist & Tasklist
		s.mypromptbox = awful.widget.prompt()
		s.mylayoutbox = awful.widget.layoutbox(s)
		s.mylayoutbox:buttons(gears.table.join(
			awful.button({}, 1, function()
				awful.layout.inc(1)
			end),
			awful.button({}, 3, function()
				awful.layout.inc(-1)
			end)
		))

		s.mytaglist = awful.widget.taglist({
			screen = s,
			filter = awful.widget.taglist.filter.all,
			buttons = bar.taglist_buttons,
		})

		s.mytasklist = awful.widget.tasklist({
			screen = s,
			filter = awful.widget.tasklist.filter.currenttags,
			buttons = bar.tasklist_buttons,
		})

		-- Create a wibox (top bar)
		local side_margin = dpi(24)
		s.mywibox = awful.wibar({
			position = "top",
			screen = s,
			x = side_margin,
			width = s.geometry.width - 2 * side_margin,
			height = dpi(24),
			bg = beautiful.bg_normal,
			fg = beautiful.fg_normal,
		})

		-- We can place the CPU, Mem, Temp, Net, Volume, DateTime, FocusedClass, etc. on the "right" side
		-- using arrow() calls in between for style transitions.

		s.mywibox:setup({
			layout = wibox.layout.align.horizontal,
			expand = "none",

			{ -- Left widgets
				layout = wibox.layout.fixed.horizontal,
				wibox.container.margin(s.mytaglist, dpi(10), 0, 0, 0), -- Adds 10dpi of left margin
				s.mypromptbox,
				wibox.container.margin(waWidget, dpi(8), 0, 0, 0),
			},

			-- Middle widget: a centered "Focused Window Class"
			wibox.container.place(focused_window_class),

			{
				-- Right widgets
				layout = wibox.layout.fixed.horizontal,
				-- CPU
				wibox.container.background(
					wibox.container.margin(
						wibox.widget({ cpuicon, cpu.widget, layout = wibox.layout.align.horizontal }),
						3,
						3
					),
					beautiful.bg_normal
				),

				-- Memory
				wibox.container.background(
					wibox.container.margin(
						wibox.widget({ memicon, mem.widget, layout = wibox.layout.align.horizontal }),
						3,
						3
					),
					beautiful.bg_normal
				),

				-- Network
				wibox.container.background(
					wibox.container.constraint(
						wibox.container.place(wibox.container.margin(
							wibox.widget({
								neticon,
								net.widget,
								layout = wibox.layout.align.horizontal,
							}),
							3,
							3
						)),
						"exact", -- width strategy
						100 -- set your desired fixed width
					),
					beautiful.bg_normal
				),

				-- Volume
				wibox.container.background(
					wibox.container.margin(
						wibox.widget({ nil, volume_widget, layout = wibox.layout.align.horizontal }),
						3,
						3
					),
					beautiful.bg_normal
				),

				wibox.container.background(
					wibox.container.constraint(
						wibox.container.place(wibox.container.margin(
							wibox.widget({
								systray,
								layout = wibox.layout.align.horizontal,
							}),
							3,
							3
						)),
						"exact", -- width strategy
						100 -- set your desired fixed width
					),
					beautiful.bg_normal
				),

				-- Date/Time
				wibox.container.background(wibox.container.margin(date_time_widget, 10, 10), beautiful.bg_normal),
			},
		})
	end)
end

return bar
