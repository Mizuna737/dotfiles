# ~/.config/qutebrowser/config.py

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
