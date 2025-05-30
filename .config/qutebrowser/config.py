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

# Bind “gy” to open YouTube in the current tab
config.bind("gy", "open https://www.youtube.com/")

# Bind “gY” to open YouTube in a new tab
config.bind("gY", "open -t https://www.youtube.com/")

# toggle between multiple  ↔  switching
config.bind("tt", "spawn --userscript toggleTabs.py")

config.source("userscripts/wal.py")

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

# map search keywords → URLs
c.url.searchengines = {
    "DEFAULT": "https://www.google.com/search?q={}",  # what you get if you type :open something
    "g": "https://www.google.com/search?q={}",  # explicit “g”
    "ddg": "https://duckduckgo.com/?q={}",  # keep DuckDuckGo if you like
    # add more as you like...
}


# Open ChatGPT on startup
c.url.start_pages = ["https://chat.openai.com/"]

# Use ChatGPT as the default page (for :open or new-tab)
c.url.default_page = "https://chat.openai.com/"
