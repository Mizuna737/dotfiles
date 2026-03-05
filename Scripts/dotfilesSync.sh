#!/bin/bash

DOTFILES_DIR="$HOME/dotfiles"

cd "$DOTFILES_DIR" || {
  echo "Error: Could not cd into $DOTFILES_DIR"
  exit 1
}

# Check for any changes (staged, unstaged, or untracked)
gitStatus=$(git status --porcelain)

if [ -z "$gitStatus" ]; then
  echo "Nothing to sync — working tree clean."
  exit 0
fi

echo "Changes detected:"
git status --short
echo ""

# If there are new (untracked) files, re-stow to create symlinks
untrackedFiles=$(git ls-files --others --exclude-standard)

if [ -n "$untrackedFiles" ]; then
  echo "New files detected — re-stowing $DOTFILES_DIR..."
  stow --target="$HOME" . 2>&1
  if [ $? -ne 0 ]; then
    echo "Error: stow failed. Resolve conflicts before syncing."
    exit 1
  fi
  echo "Stow complete."
  echo ""
fi

# Stage all changes
git add -A

# Prompt for commit message
echo -n "Commit message: "
read -r commitMsg

if [ -z "$commitMsg" ]; then
  echo "Error: Commit message cannot be empty."
  exit 1
fi

# Commit
git commit -m "$commitMsg"

# Push
echo ""
echo "Pushing to remote..."
git push

if [ $? -eq 0 ]; then
  echo "Done — dotfiles synced successfully."
else
  echo "Error: Push failed. Check your remote/auth config."
  exit 1
fi
