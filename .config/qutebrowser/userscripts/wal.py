# ~/.config/qutebrowser/config.d/wal.py

import os


def get_color(name, default):
    return os.environ.get(name, default)


c.colors.statusbar.normal.bg = get_color("WAL_COLOR0", "#1F2430")
c.colors.statusbar.normal.fg = get_color("WAL_FOREGROUND", "#CBCCC6")

c.colors.statusbar.insert.bg = get_color("WAL_COLOR2", "#BAE67E")
c.colors.statusbar.insert.fg = get_color("WAL_COLOR0", "#1F2430")

c.colors.tabs.bar.bg = get_color("WAL_COLOR0", "#1F2430")
c.colors.tabs.selected.even.bg = get_color("WAL_COLOR4", "#5CCFE6")
c.colors.tabs.selected.even.fg = get_color("WAL_COLOR0", "#1F2430")
c.colors.tabs.odd.bg = get_color("WAL_COLOR1", "#F28779")
c.colors.tabs.odd.fg = get_color("WAL_FOREGROUND", "#CBCCC6")

c.colors.completion.category.bg = get_color("WAL_COLOR8", "#5C6773")
c.colors.completion.item.selected.bg = get_color("WAL_COLOR4", "#5CCFE6")

c.colors.hints.bg = get_color("WAL_COLOR3", "#E6B450")
c.colors.hints.fg = get_color("WAL_COLOR0", "#1F2430")

# Optional: content dark mode
c.colors.webpage.bg = get_color("WAL_COLOR0", "#1F2430")
config.set("colors.webpage.darkmode.enabled", True)
