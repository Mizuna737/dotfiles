-- stack.lua
-- Tabbed window stacking for AwesomeWM.
--
-- The active window is always the anchor: it holds the tiling slot and is
-- the only visible frame member. All inactive members are hidden (hidden=true).
-- Cycling promotes the new window to anchor via makeAnchor (swap + retile),
-- which triggers picom's show/hide animations for a crossfade effect.
-- Because the active window is always tiling in its slot, unstack* is safe.

local awful    = require("awful")
local gears    = require("gears")
local wibox    = require("wibox")
local beautiful = require("beautiful")
local myFuncs  = require("functions")

local M = {}

local _tempStackTimer = nil
local TEMP_STACK_TIMEOUT = 0.75 -- seconds before auto-unstack

-- frame = {
--   clients   = { c, ... },
--   activeIdx = int,
--   anchor    = client,   -- always the active window; holds the tiling slot
-- }
local clientFrame = setmetatable({}, { __mode = "k" })

local TAB_H = 22

-------------------------------------------------------------------------
-- Forward declaration
-------------------------------------------------------------------------
local setActive

-------------------------------------------------------------------------
-- Tab bar — rebuilt on ALL frame members so hidden windows keep their
-- titlebar rendered and don't re-render when cycled into focus.
-------------------------------------------------------------------------

local function rebuildTabbar(frame)
	for _, c in ipairs(frame.clients) do
		if not c.valid then
			goto continue
		end
		local tabs = { layout = wibox.layout.flex.horizontal }
		for i, fc in ipairs(frame.clients) do
			local isActive = (i == frame.activeIdx)
			local idx = i
			local tab = wibox.widget({
				{
					text = fc.class or fc.name or "?",
					align = "center",
					valign = "center",
					widget = wibox.widget.textbox,
				},
				bg = isActive and beautiful.bg_focus or beautiful.bg_normal,
				fg = isActive and beautiful.fg_focus or beautiful.fg_normal,
				widget = wibox.container.background,
			})
			tab:connect_signal("button::press", function(_, _, _, btn)
				if btn == 1 then
					setActive(frame, idx)
				end
			end)
			table.insert(tabs, tab)
		end
		local tb = awful.titlebar(c, { size = TAB_H, position = "top" })
		tb:setup(tabs)
		awful.titlebar.show(c)
		::continue::
	end
end

local function hideTabbar(c)
	if c and c.valid then
		awful.titlebar.hide(c)
	end
end

-------------------------------------------------------------------------
-- Frame helpers
-------------------------------------------------------------------------

-- Promote c to anchor by sliding it into the tiling slot.
-- Order matters: hide old first so it leaves tiling invisibly, then swap
-- list positions while both are excluded from tiling (no reflow), then tile c.
local function makeAnchor(frame, c)
	if c == frame.anchor then
		return
	end
	local old = frame.anchor

	-- Detach the geometry-mirror signal from the outgoing anchor.
	if frame._geomMirror and old and old.valid then
		old:disconnect_signal("property::geometry", frame._geomMirror)
	end
	frame._geomMirror = nil

	-- Snapshot the tile geometry before any layout state changes.
	local geom = (old and old.valid) and old:geometry() or nil

	old.hidden = true -- remove old from tiling layout invisibly
	old.floating = true -- mark as float so it re-appears correctly later
	c:swap(old) -- swap client-list positions (both excluded from tiling, no reflow)

	-- Pre-seed c's geometry so the tiling layout has no stale position to snap from.
	-- Must happen after swap (so c is in old's list slot) but before floating=false
	-- (which triggers the layout pass). If floating=false resets geometry anyway,
	-- the apply after hidden=false in setActive will catch it.
	if geom then
		c:geometry(geom)
	end

	c.floating = false -- c enters tiling at old's former list position
	frame.anchor = c

	-- Attach a geometry-mirror signal to the new anchor so stashed members
	-- always carry the current tile geometry and arrive without a snap when promoted.
	-- Capture only the frame table (strong ref); re-read frame.anchor inside handler
	-- so we never extend the lifetime of any client via a closure strong-ref.
	local mirrorHandler = function()
		local anchor = frame.anchor
		if not anchor or not anchor.valid then return end
		local g = anchor:geometry()
		for _, m in ipairs(frame.clients) do
			if m ~= anchor and m.valid then
				m:geometry(g)
			end
		end
	end
	frame._geomMirror = mirrorHandler
	c:connect_signal("property::geometry", mirrorHandler)
end

local function removeFromFrame(frame, c)
	for i, cl in ipairs(frame.clients) do
		if cl == c then
			table.remove(frame.clients, i)
			if frame.activeIdx > i then
				frame.activeIdx = frame.activeIdx - 1
			end
			frame.activeIdx = math.max(1, math.min(frame.activeIdx, #frame.clients))
			break
		end
	end
	clientFrame[c] = nil
end

local function dissolveFrame(frame)
	-- Detach the geometry-mirror signal before dissolving so the handler doesn't
	-- fire on clients that are about to leave the frame.
	if frame._geomMirror and frame.anchor and frame.anchor.valid then
		frame.anchor:disconnect_signal("property::geometry", frame._geomMirror)
	end
	frame._geomMirror = nil

	for _, c in ipairs(frame.clients) do
		clientFrame[c] = nil
		if c.valid then
			c.floating = false -- tiling before reveal so window enters layout directly
			c.hidden = false
			hideTabbar(c)
		end
	end
end

-------------------------------------------------------------------------
-- setActive: promote new window to anchor on every cycle.
-- makeAnchor hides the old anchor (picom fade out) and tiles the new one.
-- Revealing the new anchor (picom fade in) completes the crossfade.
-- Because the active window is always the anchor, unstack* is trivially safe.
-------------------------------------------------------------------------

setActive = function(frame, newIdx)
	if newIdx < 1 or newIdx > #frame.clients then
		return
	end
	if newIdx == frame.activeIdx then
		return
	end

	local newActive = frame.clients[newIdx]
	if not newActive.valid then
		return
	end

	-- Capture tile geometry before makeAnchor modifies layout state.
	-- Re-apply after makeAnchor so that if floating=false reset c's geometry,
	-- the correct position is restored before the first paint on un-hide.
	local preGeom = frame.anchor.valid and frame.anchor:geometry() or nil
	makeAnchor(frame, newActive) -- old anchor: hidden=true (fade out); newActive: tiling
	if preGeom then newActive:geometry(preGeom) end
	newActive.hidden = false -- reveal: picom fade in
	newActive:raise()

	frame.activeIdx = newIdx
	client.focus = newActive
	rebuildTabbar(frame)
end

-------------------------------------------------------------------------
-- Auto-cleanup when a framed client is closed
-------------------------------------------------------------------------

client.connect_signal("unmanage", function(c)
	local frame = clientFrame[c]
	if not frame then
		return
	end

	local wasAnchor = (c == frame.anchor)
	removeFromFrame(frame, c)

	if #frame.clients == 0 then
		return
	elseif #frame.clients == 1 then
		dissolveFrame(frame)
		return
	end

	-- Active window is always the anchor; promote a replacement and reveal it.
	local newActive = frame.clients[frame.activeIdx]
	if newActive and newActive.valid then
		newActive.floating = false
		newActive.hidden = false
		frame.anchor = newActive
		newActive:raise()
		client.focus = newActive
		rebuildTabbar(frame)
	end
end)

-------------------------------------------------------------------------
-- Public API
-------------------------------------------------------------------------

-- Return the frame for a given client, or nil if not in a frame.
function M.getFrameForClient(c)
	return clientFrame[c]
end

-- Programmatically create a frame from an explicit client list.
-- clients: ordered list of clients; activeIdx: 1-based index of the anchor.
-- opts (optional): table of extra keys to copy onto the frame:
--   isRelated, isGlobal, homeTags, originTag, priorFrames
function M.createFrame(clients, activeIdx, opts)
	if not clients or #clients < 2 then return end
	activeIdx = activeIdx or 1

	-- Clear any existing frames these clients belong to
	local seenFrames = {}
	for _, c in ipairs(clients) do
		local f = clientFrame[c]
		if f and not seenFrames[f] then
			seenFrames[f] = true
			for _, fc in ipairs(f.clients) do
				hideTabbar(fc)
			end
		end
		clientFrame[c] = nil
	end

	local anchor = clients[activeIdx]
	local frame = { clients = clients, activeIdx = activeIdx, anchor = anchor }

	if opts then
		for _, key in ipairs({ "isRelated", "isGlobal", "homeTags", "originTag", "priorFrames" }) do
			if opts[key] ~= nil then
				frame[key] = opts[key]
			end
		end
	end

	local anchorGeom = anchor.valid and anchor:geometry() or nil
	for i, c in ipairs(clients) do
		clientFrame[c] = frame
		if i ~= activeIdx then
			-- Pre-seed stash geometry so the client arrives at the correct tile
			-- position if it is later promoted to anchor via makeAnchor.
			if anchorGeom then c:geometry(anchorGeom) end
			c.floating = true
			c.hidden = true
		else
			c.hidden = false
			c.floating = false
		end
	end

	anchor:raise()
	client.focus = anchor
	rebuildTabbar(frame)
end

-- Stack every eligible client on the current tag into one frame.
-- "Eligible" = not floating, OR already in a frame (frame floats are ok).
function M.stackAll()
	myFuncs.focusMaster()
	local t = awful.screen.focused().selected_tag
	if not t then
		return
	end
	local cls = t:clients()
	if #cls < 2 then
		return
	end

	local allClients = {}
	local seen = {}
	local affectedFrames = {}
	local priorFrames = {}
	local snapshotted = {}

	for _, c in ipairs(cls) do
		local inFrame = clientFrame[c] ~= nil
		if not seen[c] and (not c.floating or inFrame) then
			seen[c] = true
			local f = clientFrame[c]
			if f then
				affectedFrames[f] = true
				-- Capture predecessor frames for later restore by unstackAll.
				-- Skip isRelated/isGlobal frames — their dispersal semantics are special.
				if not f.isRelated and not f.isGlobal and not snapshotted[f] then
					snapshotted[f] = true
					if f.priorFrames then
						-- f was itself a mega-frame; inherit its priors to keep
						-- repeated stackAll/unstackAll round-trips idempotent.
						for _, prior in ipairs(f.priorFrames) do
							table.insert(priorFrames, prior)
						end
					else
						local copy = {}
						for _, fc in ipairs(f.clients) do
							table.insert(copy, fc)
						end
						table.insert(priorFrames, { clients = copy, activeIdx = f.activeIdx })
					end
				end
			end
			clientFrame[c] = nil
			table.insert(allClients, c)
		end
	end

	for f in pairs(affectedFrames) do
		for _, c in ipairs(f.clients) do
			hideTabbar(c)
		end
	end

	if #allClients < 2 then
		return
	end

	local focusedIdx = 1
	local fc = client.focus
	for i, c in ipairs(allClients) do
		if c == fc then
			focusedIdx = i
			break
		end
	end

	local anchor = allClients[focusedIdx]
	local frame = { clients = allClients, activeIdx = focusedIdx, anchor = anchor }
	if #priorFrames > 0 then
		frame.priorFrames = priorFrames
	end

	for _, c in ipairs(allClients) do
		clientFrame[c] = frame
	end

	-- Anchor: ensure tiling and visible
	anchor.hidden = false
	anchor.floating = false

	-- Others: mark as float and hide — makeAnchor tiles them when cycled to.
	-- Pre-seed stash geometry so promotion via makeAnchor has no snap.
	local anchorGeom = anchor.valid and anchor:geometry() or nil
	for i, c in ipairs(allClients) do
		if i ~= focusedIdx then
			if anchorGeom then c:geometry(anchorGeom) end
			c.floating = true
			c.hidden = true
		end
	end

	anchor:raise()
	client.focus = anchor
	rebuildTabbar(frame)
end

-- Peel the focused client off its frame.
-- For isRelated frames: sends all remaining clients back to their home tags.
-- For isGlobal frames: moves the unstacked client to the origin tag.
-- For normal frames: the rest of the frame continues as-is.
function M.unstackCurrent()
	local c = client.focus
	if not c then
		return
	end
	local frame = clientFrame[c]
	if not frame then
		return
	end

	makeAnchor(frame, c)
	removeFromFrame(frame, c)
	hideTabbar(c)

	if frame.isRelated then
		for _, cl in ipairs(frame.clients) do
			clientFrame[cl] = nil
			if cl.valid then
				cl.floating = false
				cl.hidden = false
				hideTabbar(cl)
				local ht = frame.homeTags[cl]
				if ht and ht.valid then
					cl:move_to_tag(ht)
				end
			end
		end
		client.focus = c
		c:raise()
		return
	end

	if frame.isGlobal then
		if frame.originTag and frame.originTag.valid then
			c:move_to_tag(frame.originTag)
		end
		if #frame.clients == 0 then
			-- nothing
		elseif #frame.clients == 1 then
			dissolveFrame(frame)
		else
			local newActive = frame.clients[frame.activeIdx]
			if newActive and newActive.valid then
				newActive.floating = false
				newActive.hidden = false
				frame.anchor = newActive
				newActive:raise()
				rebuildTabbar(frame)
			end
		end
		client.focus = c
		c:raise()
		return
	end

	-- Normal frame: the rest continues
	if #frame.clients == 0 then
		return
	elseif #frame.clients == 1 then
		dissolveFrame(frame)
	else
		local newActive = frame.clients[frame.activeIdx]
		if newActive and newActive.valid then
			newActive.floating = false
			newActive.hidden = false
			frame.anchor = newActive
			newActive:raise()
			rebuildTabbar(frame)
		end
	end

	client.focus = c
	c:raise()
end

-- Dissolve the frame entirely.
-- For isRelated/isGlobal frames: sends all clients back to their home tags.
-- For normal frames: returns all clients to the tiling layout on the current tag.
function M.unstackAll()
	local c = client.focus
	if not c then
		return
	end
	local frame = clientFrame[c]
	if not frame then
		return
	end

	makeAnchor(frame, c)

	if frame.isRelated or frame.isGlobal then
		local originTag = frame.originTag
		for _, cl in ipairs(frame.clients) do
			clientFrame[cl] = nil
			if cl.valid then
				cl.floating = false
				cl.hidden = false
				hideTabbar(cl)
				local ht = frame.homeTags[cl]
				if ht and ht.valid then
					cl:move_to_tag(ht)
				end
			end
		end
		if frame.isGlobal and originTag and originTag.valid then
			originTag:view_only()
		else
			client.focus = c
			c:raise()
		end
		return
	end

	dissolveFrame(frame)

	if frame.priorFrames and #frame.priorFrames > 0 then
		local t = awful.screen.focused().selected_tag
		local tagClients = {}
		if t then
			for _, tc in ipairs(t:clients()) do
				tagClients[tc] = true
			end
		end

		for _, snapshot in ipairs(frame.priorFrames) do
			local filtered = {}
			for _, sc in ipairs(snapshot.clients) do
				if sc.valid and tagClients[sc] then
					table.insert(filtered, sc)
				end
			end
			if #filtered >= 2 then
				local idx = math.max(1, math.min(snapshot.activeIdx, #filtered))
				M.createFrame(filtered, idx)
			end
		end
	end

	client.focus = c
	c:raise()
end

-- Cycle forward through the frame containing the focused client.
function M.cycleStackForward()
	local c = client.focus
	if not c then
		return
	end
	local frame = clientFrame[c]
	if not frame then
		return
	end
	setActive(frame, (frame.activeIdx % #frame.clients) + 1)
end

-- Cycle backward through the frame containing the focused client.
function M.cycleStackBackward()
	local c = client.focus
	if not c then
		return
	end
	local frame = clientFrame[c]
	if not frame then
		return
	end
	setActive(frame, ((frame.activeIdx - 2 + #frame.clients) % #frame.clients) + 1)
end

-- Return the number of clients in the frame containing the focused window, or 0.
function M.stackFrameSize()
	local c = client.focus
	if not c then return 0 end
	local frame = clientFrame[c]
	if not frame then return 0 end
	return #frame.clients
end

-- Activate a specific 1-based slot index in the frame containing the focused window.
function M.stackActivate(idx)
	local c = client.focus
	if not c then return end
	local frame = clientFrame[c]
	if not frame then return end
	setActive(frame, idx)
end

-------------------------------------------------------------------------
-- Temp stack: stack all on first press, cycle on repeat, auto-unstack
-- after TEMP_STACK_TIMEOUT seconds of inactivity.
-------------------------------------------------------------------------
function M.tempStack()
	if _tempStackTimer then
		_tempStackTimer:stop()
		_tempStackTimer = nil
		M.cycleStackForward()
	else
		M.stackAll()
	end

	_tempStackTimer = gears.timer.start_new(TEMP_STACK_TIMEOUT, function()
		M.unstackAll()
		_tempStackTimer = nil
		return false
	end)
end

-------------------------------------------------------------------------
-- Stack all clients with the same class as the focused window.
-- Pulls them from any tag to the current tag. Unstacking sends them back.
-------------------------------------------------------------------------
function M.stackRelated()
	local c = client.focus
	if not c then
		return
	end
	local targetClass = c.class
	if not targetClass then
		return
	end
	local currentTag = awful.screen.focused().selected_tag
	if not currentTag then
		return
	end

	local homeTags = {}
	local toStack = {}
	local seen = {}

	for _, cl in ipairs(client.get()) do
		if cl.valid and not seen[cl] and (cl.class or "") == targetClass then
			seen[cl] = true
			homeTags[cl] = cl.first_tag or currentTag
			if cl.first_tag ~= currentTag then
				cl:move_to_tag(currentTag)
			end
			table.insert(toStack, cl)
		end
	end

	if #toStack < 2 then
		for cl, ht in pairs(homeTags) do
			if ht ~= currentTag then
				cl:move_to_tag(ht)
			end
		end
		return
	end

	local seenFrames = {}
	for _, cl in ipairs(toStack) do
		local f = clientFrame[cl]
		if f and not seenFrames[f] then
			seenFrames[f] = true
			for _, fc in ipairs(f.clients) do
				hideTabbar(fc)
			end
		end
		clientFrame[cl] = nil
	end

	local focusedIdx = 1
	for i, cl in ipairs(toStack) do
		if cl == c then
			focusedIdx = i
			break
		end
	end

	local anchor = toStack[focusedIdx]
	local frame = {
		clients = toStack,
		activeIdx = focusedIdx,
		anchor = anchor,
		isRelated = true,
		homeTags = homeTags,
	}
	for _, cl in ipairs(toStack) do
		clientFrame[cl] = frame
	end

	anchor.hidden = false
	anchor.floating = false
	local anchorGeomR = anchor.valid and anchor:geometry() or nil
	for i, cl in ipairs(toStack) do
		if i ~= focusedIdx then
			if anchorGeomR then cl:geometry(anchorGeomR) end
			cl.floating = true
			cl.hidden = true
		end
	end

	anchor:raise()
	client.focus = anchor
	rebuildTabbar(frame)
end

-------------------------------------------------------------------------
-- Stack all clients across all tags into one frame on the current tag.
-- Second call restores each client to its original tag and focuses origin.
-- unstackCurrent during a global stack moves the window to the origin tag.
-------------------------------------------------------------------------
function M.stackAllGlobal()
	local c = client.focus
	local frame = c and clientFrame[c]

	-- Toggle off: restore everything
	if frame and frame.isGlobal then
		local originTag = frame.originTag
		for _, cl in ipairs(frame.clients) do
			clientFrame[cl] = nil
			if cl.valid then
				cl.floating = false
				cl.hidden = false
				hideTabbar(cl)
				local ht = frame.homeTags[cl]
				if ht and ht.valid then
					cl:move_to_tag(ht)
				end
			end
		end
		if originTag and originTag.valid then
			originTag:view_only()
		end
		return
	end

	-- Toggle on: pull everything to current tag and stack
	local currentTag = awful.screen.focused().selected_tag
	if not currentTag then
		return
	end

	local homeTags = {}
	local toStack = {}
	local seen = {}

	for _, cl in ipairs(client.get()) do
		if cl.valid and not cl.hidden and not cl.floating and cl.screen == screen.primary and not seen[cl] then
			seen[cl] = true
			homeTags[cl] = cl.first_tag or currentTag
			if cl.first_tag ~= currentTag then
				cl:move_to_tag(currentTag)
			end
			table.insert(toStack, cl)
		end
	end

	if #toStack < 2 then
		for cl, ht in pairs(homeTags) do
			if ht ~= currentTag then
				cl:move_to_tag(ht)
			end
		end
		return
	end

	local seenFrames = {}
	for _, cl in ipairs(toStack) do
		local f = clientFrame[cl]
		if f and not seenFrames[f] then
			seenFrames[f] = true
			for _, fc in ipairs(f.clients) do
				hideTabbar(fc)
			end
		end
		clientFrame[cl] = nil
	end

	local focusedIdx = 1
	for i, cl in ipairs(toStack) do
		if cl == c then
			focusedIdx = i
			break
		end
	end

	local anchor = toStack[focusedIdx]
	local newFrame = {
		clients = toStack,
		activeIdx = focusedIdx,
		anchor = anchor,
		isGlobal = true,
		homeTags = homeTags,
		originTag = currentTag,
	}
	for _, cl in ipairs(toStack) do
		clientFrame[cl] = newFrame
	end

	anchor.hidden = false
	anchor.floating = false
	local anchorGeomG = anchor.valid and anchor:geometry() or nil
	for i, cl in ipairs(toStack) do
		if i ~= focusedIdx then
			if anchorGeomG then cl:geometry(anchorGeomG) end
			cl.floating = true
			cl.hidden = true
		end
	end

	anchor:raise()
	client.focus = anchor
	rebuildTabbar(newFrame)
end

return M
