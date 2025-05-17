-- devices/macropad.lua
-- 5-button pad with short press vs. long press. 
-- Assume short press => F21..F25, long press => F26..F30.

local gears = require("gears")
local awful = require("awful")
local myFuncs = require("functions")
-- Modifiers:
local modkey = "Mod4"  -- Super
local ctrl   = "Control"
local altkey = "Mod1"
local shft   = "Shift"

local macropad = {}

macropad.globalkeys = gears.table.join(
    -- Button 1 short => Meta+Alt+1 => Load Entertainment Config
    awful.key({modkey, altkey}, "7", function()
        myFuncs.loadWorkspaceConfiguration("Entertainment")
    end, {description = "M1 => load Entertainment configuration", group = "macropad"}),
    -- Button 1 long => Meta+Alt+Control+1 => Save Entertainment Config
    awful.key({modkey, altkey, ctrl}, "7", function()
        myFuncs.saveWorkspaceConfiguration("Entertainment")
    end, {description = "M1 hold => overwrite Entertainment configuration", group = "macropad"}),
    -- Button 2 short => Meta+Alt+2 => Load Code Config
    awful.key({modkey, altkey}, "8", function()
        myFuncs.loadWorkspaceConfiguration("Code")
    end, {description = "M2 => load Code configuration", group = "macropad"}),
    -- Button 2 long => Meta+Alt+Control+2 => Save Code Config
    awful.key({modkey, altkey, ctrl}, "8", function()
        myFuncs.saveWorkspaceConfiguration("Code")
    end, {description = "M2 hold => overwrite Code configuration", group = "macropad"}),
    -- Button 3 short => Meta+Alt+2 => Load Work Config
    awful.key({modkey, altkey}, "0", function()
        myFuncs.loadWorkspaceConfiguration("Work")
    end, {description = "M3 => load Work configuration", group = "macropad"}),
    -- Button 3 long => Meta+Alt+Control+1 => Save Work Config
    awful.key({modkey, altkey, ctrl}, "0", function()
        myFuncs.saveWorkspaceConfiguration("Work")
    end, {description = "M3 hold => overwrite Work configuration", group = "macropad"}),
    -- Button 2 short => Meta+Alt+4 => Load Work Config
    awful.key({modkey, altkey}, "-", function()
        myFuncs.loadWorkspaceConfiguration("Obsidian")
    end, {description = "M4 => load Obsidian configuration", group = "macropad"}),
    -- Button 2 long => Meta+Alt+Control+4 => Save Obsidian Config
    awful.key({modkey, altkey, ctrl}, "-", function()
        myFuncs.saveWorkspaceConfiguration("Obsidian")
    end, {description = "M4 hold => overwrite Obsidian configuration", group = "macropad"}),
    -- Button 2 short => Meta+Alt+5 => Load Work Config
    awful.key({modkey, altkey}, "=", function()
        myFuncs.loadWorkspaceConfiguration("Misc")
    end, {description = "M5 => load Misc configuration", group = "macropad"}),
    -- Button 2 long => Meta+Alt+Control+5 => Save Misc Config
    awful.key({modkey, altkey, ctrl}, "=", function()
        myFuncs.saveWorkspaceConfiguration("Misc")
    end, {description = "M5 hold => overwrite Misc configuration", group = "macropad"})
)

return macropad
