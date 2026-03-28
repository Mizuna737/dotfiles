-- ~/.config/luakit/userconf.lua
local window = require("window")
window.add_signal("init", function(w)
	w.tablist.widget:hide()
	w.bar_layout:hide()
end)
