# ~/.config/qutebrowser/config.py

config.load_autoconfig()
import os, re


# 1) Locate your quickmarks file (plaintext format)
config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
qm_path = os.path.join(
    config_home, "qutebrowser", "quickmarks"
)  # :contentReference[oaicite:0]{index=0}

# 2) Read & parse each line, extracting URL and name
bills_urls = []
if os.path.exists(qm_path):
    with open(qm_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Find the first http(s)://… chunk
            match = re.search(r"(https?://\S+)", line)
            if match and "Bills" in line:
                bills_urls.append(match.group(1))

# 3) Build your command string: open each URL in a new tab
if bills_urls:
    cmd = ";;".join(f"open --tab {url}" for url in bills_urls)
else:
    cmd = 'message-info "No Bills quickmarks found"'

# 4) Bind it to ,b so you can verify with :bind ,b
config.bind(
    ",b", cmd
)  # opens all your “(Bills)” URLs in tabs :contentReference[oaicite:1]{index=1}

palette = {
    "bg": "#1f2430",
    "fg": "#cad3f5",
    "selection": "#333b5a",
    "comment": "#5c6773",
    "cyan": "#70c0ba",
    "green": "#60c766",
    "orange": "#ff966c",
    "pink": "#f280a1",
    "purple": "#b4befe",
    "red": "#ec5f67",
    "yellow": "#d5a067",
}

# --- tabs: selected & unselected (even/odd) ---
c.colors.tabs.bar.bg = palette["bg"]

# selected tabs
c.colors.tabs.selected.even.bg = palette["selection"]
c.colors.tabs.selected.even.fg = palette["fg"]
c.colors.tabs.selected.odd.bg = palette["selection"]
c.colors.tabs.selected.odd.fg = palette["fg"]

# unselected tabs
c.colors.tabs.even.bg = palette["bg"]
c.colors.tabs.even.fg = palette["comment"]
c.colors.tabs.odd.bg = palette["bg"]
c.colors.tabs.odd.fg = palette["comment"]

# (optional) pinned tabs if you use them
# c.colors.tabs.pinned.even.bg             = palette['orange']
# c.colors.tabs.pinned.even.fg             = palette['bg']
# c.colors.tabs.pinned.odd.bg              = palette['orange']
# c.colors.tabs.pinned.odd.fg              = palette['bg']
# c.colors.tabs.pinned.selected.even.bg    = palette['selection']
# c.colors.tabs.pinned.selected.even.fg    = palette['fg']
# c.colors.tabs.pinned.selected.odd.bg     = palette['selection']
# c.colors.tabs.pinned.selected.odd.fg     = palette['fg']

# --- statusbar URL success colors (HTTP vs HTTPS) ---
c.colors.statusbar.url.success.http.fg = palette["green"]
c.colors.statusbar.url.success.https.fg = palette["cyan"]

# (rest of your theme…)
c.colors.statusbar.normal.bg = palette["bg"]
c.colors.statusbar.normal.fg = palette["fg"]
c.colors.statusbar.insert.bg = palette["cyan"]
c.colors.statusbar.insert.fg = palette["bg"]
c.colors.statusbar.command.bg = palette["selection"]
c.colors.statusbar.command.fg = palette["fg"]
c.colors.statusbar.passthrough.bg = palette["orange"]
c.colors.statusbar.passthrough.fg = palette["bg"]

c.colors.completion.category.bg = palette["bg"]
c.colors.completion.category.fg = palette["purple"]
c.colors.completion.even.bg = palette["bg"]
c.colors.completion.odd.bg = palette["bg"]
c.colors.completion.fg = palette["fg"]
c.colors.completion.match.fg = palette["yellow"]

c.colors.messages.info.bg = palette["bg"]
c.colors.messages.info.fg = palette["cyan"]
c.colors.messages.warning.bg = palette["bg"]
c.colors.messages.warning.fg = palette["yellow"]
c.colors.messages.error.bg = palette["bg"]
c.colors.messages.error.fg = palette["red"]

c.colors.prompts.bg = palette["bg"]
c.colors.prompts.fg = palette["fg"]
c.colors.prompts.selected.bg = palette["selection"]

# ---- Zenful qutebrowser tweaks ----
# Hide UI until you need it
c.tabs.show = "multiple"
c.statusbar.show = "in-mode"

# Scrolling
c.scrolling.smooth = True
c.scrolling.bar = "never"

# Minimal completion
c.completion.open_categories = ["quickmarks", "history"]
c.hints.chars = "asdfghjkl"

# Distractions off
c.content.notifications.enabled = False
c.content.autoplay = False
c.content.blocking.enabled = True
c.auto_save.session = True


# ---- Vertical Tabs ----
# Move the tab bar
c.tabs.position = "left"  # or "right"

# How wide the vertical bar is
c.tabs.width = "15%"  # Try "200px" or "12%" until it feels right

# Only show favicons (mini “Zen” mode)
c.tabs.show = "switching"  # still hides when only one tab
c.tabs.title.format = (
    "{audio}{index} {current_title}"  # use "{audio}{index} {title}" for more detail
)

# Optionally center icons/text vertically
c.tabs.padding = {"top": 5, "bottom": 5, "left": 5, "right": 5}
