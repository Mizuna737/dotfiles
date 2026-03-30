-- ~/.config/luakit/userconf.lua
local window = require("window")
window.add_signal("init", function(w)
	w.tablist.widget:hide()
	w.bar_layout:hide()

	w:add_signal("page-loaded", function()
		local uri = w.view.uri or ""
		if uri:match("eisenhower") then
			w:set_mode("passthrough")
		end
	end)
end)
