-- workspaceManager.lua
-- Handles saving and loading AwesomeWM workspace configurations.

local awful = require("awful")
local gears = require("gears")
local naughty = require("naughty")
local defaultApps = require("defaultApps")

local M = {}

local LOAD_TIMEOUT = 10 -- seconds before giving up on missing windows

--------------------------------------------------------------------------------
-- Serializer: detects array-like tables and emits {…} rather than {["1"]=…}.
--------------------------------------------------------------------------------
local function isArray(t)
	local n = 0
	for _ in pairs(t) do n = n + 1 end
	for i = 1, n do
		if t[i] == nil then return false end
	end
	return n > 0
end

function M.serializeTable(val, name, depth)
	depth = depth or 0
	local indent = string.rep("  ", depth)
	local prefix = name and (indent .. string.format("[%q] = ", tostring(name))) or indent
	if type(val) == "table" then
		local out = prefix .. "{\n"
		if isArray(val) then
			for _, v in ipairs(val) do
				out = out .. M.serializeTable(v, nil, depth + 1) .. ",\n"
			end
		else
			for k, v in pairs(val) do
				out = out .. M.serializeTable(v, tostring(k), depth + 1) .. ",\n"
			end
		end
		return out .. indent .. "}"
	elseif type(val) == "string" then
		return prefix .. string.format("%q", val)
	else
		return prefix .. tostring(val)
	end
end

--------------------------------------------------------------------------------
-- Build the slot list for the current tag.
-- Each tiling slot is either:
--   { class, name }                                  -- single window
--   { stack=true, activeIdx=N, members={{class,name},…} }  -- frame
--------------------------------------------------------------------------------
local function buildSlots(t)
	local stack = require("stack")
	local slots = {}
	local seenFrames = {}

	-- client.get() reflects tiling order (setmaster/setslave use c:swap which mutates it).
	-- t:clients() returns tag-addition order, which is wrong for our purposes.
	for _, c in ipairs(client.get()) do
		if not c.valid or c.floating or c.hidden then goto continue end

		local onTag = false
		for _, ct in ipairs(c:tags()) do
			if ct == t then onTag = true; break end
		end
		if not onTag then goto continue end

		local frame = stack.getFrameForClient(c)
		if frame then
			if frame.anchor == c and not seenFrames[frame] then
				seenFrames[frame] = true
				local members = {}
				for _, fc in ipairs(frame.clients) do
					table.insert(members, { class = fc.class or "", name = fc.name or "" })
				end
				table.insert(slots, { stack = true, activeIdx = frame.activeIdx, members = members })
			end
		else
			table.insert(slots, { class = c.class or "", name = c.name or "" })
		end

		::continue::
	end

	return slots
end

--------------------------------------------------------------------------------
-- Shared write helper used by both the direct and prompt save paths.
--------------------------------------------------------------------------------
local function writeConfig(config, filename)
	local file = io.open(filename, "w")
	if file then
		file:write("return " .. M.serializeTable(config, nil, 0))
		file:close()
	end
end

--------------------------------------------------------------------------------
-- Save Workspace Configuration.
--------------------------------------------------------------------------------
function M.saveWorkspaceConfiguration(optionalFilename)
	local s = awful.screen.focused()
	local t = s.selected_tag
	if not t then return end

	local layoutName = (t.layout and t.layout.name) or "unknown"
	for _, mapping in ipairs(layoutMapping) do
		if t.layout == mapping.func then
			layoutName = mapping.name
			break
		end
	end

	local folder = os.getenv("HOME") .. "/.config/awesome/workspaces/"
	os.execute("mkdir -p " .. folder)

	local function save(name)
		local config = {
			workspace          = name,
			layoutName         = layoutName,
			master_width_factor = t.master_width_factor,
			slots              = buildSlots(t),
		}
		writeConfig(config, folder .. name .. ".lua")
	end

	if optionalFilename and optionalFilename ~= "" then
		save(optionalFilename)
	else
		awful.prompt.run({
			prompt   = "Save workspace as: ",
			textbox  = s.mypromptbox.widget,
			exe_callback = function(input)
				if input and input ~= "" then save(input) end
			end,
		})
	end
end

--------------------------------------------------------------------------------
-- Load Workspace Configuration.
--------------------------------------------------------------------------------
function M.loadWorkspaceConfiguration(optionalFilename)
	local folder = os.getenv("HOME") .. "/.config/awesome/workspaces/"
	local config = dofile(folder .. optionalFilename .. ".lua")
	local s = awful.screen.focused()
	local wsName = optionalFilename

	-- Resolve layout function — nil means no match, keep existing tag layout
	local layoutFunc = nil
	for _, mapping in ipairs(layoutMapping) do
		if mapping.name:lower() == (config.layoutName or ""):lower() then
			layoutFunc = mapping.func
			break
		end
	end

	-- Get or create the target tag
	local targetTag = awful.tag.find_by_name(s, wsName)
	if not targetTag then
		targetTag = awful.tag.add(wsName, { screen = s, layout = layoutFunc or awful.layout.suit.tile })
	elseif layoutFunc then
		targetTag.layout = layoutFunc
	end
	targetTag.master_width_factor = config.master_width_factor or targetTag.master_width_factor

	-- Flatten slots into a unified needs list (one entry per window, including stack members)
	local needs = {}
	for _, slot in ipairs(config.slots) do
		if slot.stack then
			for memberIdx, m in ipairs(slot.members) do
				table.insert(needs, {
					class    = m.class,
					name     = m.name,
					slot     = slot,
					memberIdx = memberIdx,
					client   = nil,
				})
			end
		else
			table.insert(needs, {
				class  = slot.class,
				name   = slot.name,
				slot   = slot,
				client = nil,
			})
		end
	end

	-- Displace windows already on the target tag that aren't needed, then
	-- prefer-match windows already on the target tag before reaching across tags.
	local overflowTag = nil
	local function getOverflow()
		if not overflowTag then
			overflowTag = awful.tag.find_by_name(s, "Overflow")
			if not overflowTag then
				overflowTag = awful.tag.add("Overflow", {
					screen   = s,
					layout   = awful.layout.suit.fair,
					volatile = true,
				})
			end
		end
		return overflowTag
	end

	local claimed = {}

	local function tryMatch(c)
		-- exact match first
		for _, need in ipairs(needs) do
			if not need.client and c.class == need.class and c.name == need.name then
				need.client = c
				claimed[c] = true
				return true
			end
		end
		-- class-only fallback
		for _, need in ipairs(needs) do
			if not need.client and c.class == need.class then
				need.client = c
				claimed[c] = true
				return true
			end
		end
		return false
	end

	-- Pass 1: match from target tag (avoids displacing windows we'll need)
	for _, c in ipairs(targetTag:clients()) do
		if c.valid then tryMatch(c) end
	end

	-- Displace unclaimed windows already on the target tag
	for _, c in ipairs(targetTag:clients()) do
		if c.valid and not claimed[c] then
			c:move_to_tag(getOverflow())
		end
	end

	-- Pass 2: match from Overflow only — don't steal from live tags
	local existingOverflow = awful.tag.find_by_name(s, "Overflow")
	if existingOverflow then
		for _, c in ipairs(existingOverflow:clients()) do
			if c.valid and not claimed[c] then tryMatch(c) end
		end
	end

	-- Move all claimed clients to the target tag
	for _, need in ipairs(needs) do
		if need.client and need.client.first_tag ~= targetTag then
			need.client:move_to_tag(targetTag)
		end
	end

	-- Collect still-unmet needs and spawn missing apps
	local pending = {}
	for _, need in ipairs(needs) do
		if not need.client then
			table.insert(pending, need)
		end
	end

	local function finalize()
		local stack = require("stack")

		-- Switch to target tag now so everything that follows operates on the right tag.
		targetTag:view_only()

		-- Phase 1: pre-classify floating state before touching tiling order.
		-- Non-anchor stack members must be hidden first so they aren't counted
		-- as tiling slots when ordering runs in phase 2.
		for _, slot in ipairs(config.slots) do
			if slot.stack then
				for _, need in ipairs(needs) do
					if need.slot == slot and need.client then
						if need.memberIdx == slot.activeIdx then
							need.client.hidden  = false
							need.client.floating = false
						else
							need.client.floating = true
							need.client.hidden  = true
						end
					end
				end
			else
				for _, need in ipairs(needs) do
					if need.slot == slot and need.client then
						need.client.floating = false
						need.client.hidden  = false
						break
					end
				end
			end
		end

		-- Phase 2: set tiling order using selection sort via direct :swap() calls.
		-- setmaster/setslave are avoided because they rely on getmaster() which uses
		-- the selected tag, and because calling setslave in sequence doesn't produce
		-- a stable forward order for 4+ clients.
		local anchorOrder = {}
		for _, slot in ipairs(config.slots) do
			local anchor
			if slot.stack then
				for _, need in ipairs(needs) do
					if need.slot == slot and need.memberIdx == slot.activeIdx and need.client then
						anchor = need.client
						break
					end
				end
			else
				for _, need in ipairs(needs) do
					if need.slot == slot and need.client then
						anchor = need.client
						break
					end
				end
			end
			if anchor then
				table.insert(anchorOrder, anchor)
			end
		end

		local function getTilingClients()
			local result = {}
			for _, c in ipairs(client.get()) do
				if c.valid and not c.floating and not c.hidden then
					for _, ct in ipairs(c:tags()) do
						if ct == targetTag then
							table.insert(result, c)
							break
						end
					end
				end
			end
			return result
		end

		for targetPos, desired in ipairs(anchorOrder) do
			local current = getTilingClients()
			if current[targetPos] ~= desired then
				for actualPos = targetPos + 1, #current do
					if current[actualPos] == desired then
						desired:swap(current[targetPos])
						break
					end
				end
			end
		end

		-- Phase 3: reconstruct frames.
		for _, slot in ipairs(config.slots) do
			if slot.stack then
				local frameClients = {}
				for _, need in ipairs(needs) do
					if need.slot == slot and need.client then
						frameClients[need.memberIdx] = need.client
					end
				end
				local compact = {}
				local newActive = slot.activeIdx
				for i = 1, #slot.members do
					if frameClients[i] then
						table.insert(compact, frameClients[i])
					elseif i < slot.activeIdx then
						newActive = newActive - 1
					end
				end
				if #compact >= 2 then
					stack.createFrame(compact, math.max(1, newActive))
				end
			end
		end

		gears.timer.delayed_call(require("functions").centerMouseOnFocusedClient)
	end

	if #pending == 0 then
		gears.timer.delayed_call(finalize)
		return
	end

	-- Event-driven spawn: claim each arriving window, finalize when all pending are met
	local manageHandler
	local timedOut = false

	manageHandler = function(c)
		if timedOut then return end
		for _, need in ipairs(pending) do
			if not need.client and c.class == need.class then
				need.client = c
				c:move_to_tag(targetTag)
				-- check if all pending needs are now satisfied
				for _, n in ipairs(pending) do
					if not n.client then return end
				end
				client.disconnect_signal("manage", manageHandler)
				gears.timer.delayed_call(finalize)
				return
			end
		end
	end

	client.connect_signal("manage", manageHandler)

	-- Spawn missing apps
	for _, need in ipairs(pending) do
		local cmd = defaultApps[need.class:lower()] or need.class:lower()
		awful.spawn.with_shell(cmd)
	end

	-- Safety timeout
	gears.timer.start_new(LOAD_TIMEOUT, function()
		if timedOut then return false end
		timedOut = true
		client.disconnect_signal("manage", manageHandler)
		gears.timer.delayed_call(finalize)
		return false
	end)
end

return M
