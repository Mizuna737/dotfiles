-- colors.lua: pulls from pywal's colors.json
local json = require("dkjson")
local home = os.getenv("HOME")
local file = io.open(home .. "/.cache/wal/colors.json", "r")

if not file then
	error("Could not read pywal colors.json")
end

local content = file:read("*a")
file:close()

local wal = json.decode(content)

-- Map colors to AwesomeWM theme variables
return {
	background = wal.special.background,
	foreground = wal.special.foreground,
	cursor = wal.special.cursor,

	black = wal.colors.color0,
	red = wal.colors.color1,
	green = wal.colors.color2,
	yellow = wal.colors.color3,
	blue = wal.colors.color4,
	magenta = wal.colors.color5,
	cyan = wal.colors.color6,
	white = wal.colors.color7,
	bright_black = wal.colors.color8,
	bright_white = wal.colors.color15,
}
