#!/usr/bin/env bash
# gestureControl-setup.sh — One-time setup for gesture control.
#
# 1. Installs system D-Bus packages via pacman (needed by the Python binding).
# 2. Creates a venv with --system-site-packages so it can reach python-dbus.
# 3. Installs mediapipe and opencv into the venv.
# 4. Downloads the MediaPipe hand landmarker model.
#
# Config files are managed via stow and live in ~/.config/gestureControl/.
# Run this once after stowing the dotfiles.

set -euo pipefail

DATA_DIR="$HOME/.local/share/gestureControl"
VENV_DIR="$DATA_DIR/venv"
MODEL_FILE="$DATA_DIR/hand_landmarker.task"
MODEL_URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

echo "=== gestureControl setup ==="
echo ""

mkdir -p "$DATA_DIR"

# ── 1. System packages ─────────────────────────────────────────────────────────
echo "[1/4] System packages (python-dbus, python-gobject)..."

if pacman -Q python-dbus python-gobject &>/dev/null; then
    echo "      Already installed."
else
    echo "      Installing via pacman (requires sudo)..."
    sudo pacman -S --noconfirm python-dbus python-gobject
fi

# ── 2. Create venv ─────────────────────────────────────────────────────────────
echo "[2/4] Python venv..."

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "      Creating: $VENV_DIR"
    # --system-site-packages gives the venv access to python-dbus and python-gobject
    python3 -m venv --system-site-packages "$VENV_DIR"
else
    echo "      Already exists: $VENV_DIR"
fi

# ── 3. Python dependencies ─────────────────────────────────────────────────────
echo "[3/4] Installing mediapipe and opencv..."

"$VENV_DIR/bin/pip" install --quiet \
    "mediapipe>=0.10.30" \
    "opencv-python>=4.9"

# ── 4. Hand landmarker model ───────────────────────────────────────────────────
echo "[4/4] Hand landmarker model..."

if [[ -f "$MODEL_FILE" ]]; then
    echo "      Already exists: $MODEL_FILE"
else
    echo "      Downloading from Google..."
    curl -L --progress-bar "$MODEL_URL" -o "$MODEL_FILE"
    echo "      Saved: $MODEL_FILE"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "  Venv:    $VENV_DIR"
echo "  Model:   $MODEL_FILE"
echo "  Config:  ~/.config/gestureControl/"
echo ""
echo "Run engine (debug window shows landmarks + pose labels):"
echo "  $VENV_DIR/bin/python ~/dotfiles/Scripts/gestureControl.py --debug"
echo ""
echo "Run engine headless + action daemon (two terminals):"
echo "  $VENV_DIR/bin/python ~/dotfiles/Scripts/gestureControl.py"
echo "  $VENV_DIR/bin/python ~/dotfiles/Scripts/gestureControl-actions.py"
echo ""
echo "Options:"
echo "  --input /dev/video2   use a specific camera device"
echo "  --config PATH         override config file location"
echo "  --dwell 300           (engine only) override default dwell time in ms"
