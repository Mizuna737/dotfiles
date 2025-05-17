#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

source $HOME/.bash_aliases

alias ls='ls --color=auto'
alias grep='grep --color=auto'
PS1='[\u@\h \W]\$ '
export LIBVIRT_DEFAULT_URI="qemu:///system"

# Created by `pipx` on 2024-11-09 21:36:13
export PATH="$PATH:/home/max/.local/bin"
export PATH=/usr/local/bin:$PATH
export EDITOR=nvim
export VISUAL=nvim
export BROWSER=qutebrowser
