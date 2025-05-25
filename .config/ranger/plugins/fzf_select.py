# ~/.config/ranger/plugins/fzf_select.py
from ranger.api.commands import Command
import os, subprocess


class fzf_select(Command):
    """
    :fzf_select
    Find a file or directory (including hidden ones) from home using fzf and jump to it.
    """

    def execute(self):
        # Starting directory: user home
        # fd flags:
        #   --hidden         → include hidden files & folders
        #   --no-ignore      → don't respect .gitignore, etc.
        #   --type f --type d→ include both files and directories
        cmd = (
            f"fd --hidden --no-ignore --type f --type d . '/home/max/'"
            " | sed 's|^'" + "/home/max/" + "'/||'"
            " | fzf --preview 'bat --style=numbers --color=always {}'"
        )
        fzf = self.fm.execute_command(
            cmd, universal_newlines=True, stdout=subprocess.PIPE
        )
        stdout, _ = fzf.communicate()
        if fzf.returncode != 0:
            return

        target = os.path.join("/home/max", stdout.strip())
        if os.path.isdir(target):
            self.fm.cd(target)
        else:
            self.fm.select_file(target)
