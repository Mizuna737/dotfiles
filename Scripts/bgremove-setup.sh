#!/usr/bin/env bash
# bgremove-setup.sh — One-time setup for GPU background removal.
# Sets up v4l2loopback output device (/dev/video21), downloads the
# Robust Video Matting ONNX model, and installs Python dependencies.

set -euo pipefail

OUTPUT_DEV_NUM=21
OUTPUT_DEV="/dev/video${OUTPUT_DEV_NUM}"
MODEL_DIR="$HOME/.local/share/bgremove"
MODEL_FILE="$MODEL_DIR/rvm_mobilenetv3.onnx"
# MobileNetV3 variant — fast enough for 30fps @ 720p on a 3080.
# Swap for rvm_resnet50.onnx for higher-quality edges (heavier).
MODEL_URL="https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"

echo "=== bgremove setup ==="
echo ""

# ── 1. v4l2loopback kernel module ────────────────────────────────────────────
echo "[1/4] v4l2loopback..."

if ! pacman -Q v4l2loopback-dkms &>/dev/null; then
  echo "      Installing v4l2loopback-dkms (AUR)..."
  paru -S --noconfirm v4l2loopback-dkms
fi

if lsmod | grep -q v4l2loopback; then
  echo "      Module already loaded."
else
  echo "      Loading module for this session..."
  sudo modprobe v4l2loopback \
    devices=1 \
    video_nr="${OUTPUT_DEV_NUM}" \
    card_label="VirtualCam-BG" \
    exclusive_caps=1
fi

# ── 2. Make v4l2loopback persistent across reboots ───────────────────────────
echo "[2/4] Persisting v4l2loopback..."

echo "v4l2loopback" | sudo tee /etc/modules-load.d/v4l2loopback-bg.conf >/dev/null
printf 'options v4l2loopback devices=1 video_nr=%d card_label="VirtualCam-BG" exclusive_caps=1\n' \
  "${OUTPUT_DEV_NUM}" | sudo tee /etc/modprobe.d/v4l2loopback-bg.conf >/dev/null

echo "      Written: /etc/modules-load.d/v4l2loopback-bg.conf"
echo "      Written: /etc/modprobe.d/v4l2loopback-bg.conf"

# ── 3. Download RVM ONNX model ───────────────────────────────────────────────
echo "[3/4] RVM model..."

mkdir -p "$MODEL_DIR"
if [[ -f "$MODEL_FILE" ]]; then
  echo "      Already exists: $MODEL_FILE"
else
  echo "      Downloading from GitHub releases…"
  curl -L --progress-bar "$MODEL_URL" -o "$MODEL_FILE"
  echo "      Saved: $MODEL_FILE"
fi

# ── 4. Python dependencies ───────────────────────────────────────────────────
echo "[4/4] Python dependencies..."

# Arch enforces PEP 668 — pip --user is blocked. Use a venv instead.
VENV_DIR="$MODEL_DIR/venv"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "      Creating venv: $VENV_DIR"
  python3 -m venv "$VENV_DIR"
else
  echo "      Venv already exists: $VENV_DIR"
fi

# onnxruntime-gpu: prefers the pip wheel (includes CUDA EP).
# TensorRT EP is available if tensorrt is also installed.
# pyfakewebcam 0.1.0 uses .tostring() which was removed in NumPy 2.0 —
# patch it after install.
"$VENV_DIR/bin/pip" install --quiet \
  "onnxruntime-gpu>=1.17" \
  "opencv-python-headless>=4.9" \
  "pyfakewebcam>=0.1"

PYFAKE="$VENV_DIR/lib/$(ls "$VENV_DIR/lib/")/site-packages/pyfakewebcam/pyfakewebcam.py"
sed -i 's/self\._buffer\.tostring()/self._buffer.tobytes()/g' "$PYFAKE"
echo "      Patched pyfakewebcam for NumPy 2.x compatibility."

echo ""
echo "=== Setup complete ==="
echo ""
echo "  Input device:   /dev/video20  (droidcam)"
echo "  Output device:  ${OUTPUT_DEV}  (VirtualCam-BG)"
echo "  Model:          ${MODEL_FILE}"
echo ""
echo "Quick test (blur background):"
echo "  python ~/dotfiles/Scripts/bgremove.py"
echo ""
echo "Enable systemd service:"
echo "  systemctl --user enable --now bgremove"
echo ""
echo "Hot-reload background without restarting:"
echo "  echo 'green' > ~/.cache/bgremove.bg && kill -USR1 \$(pgrep -f bgremove.py)"
echo "  echo '/path/to/image.jpg' > ~/.cache/bgremove.bg && kill -USR1 \$(pgrep -f bgremove.py)"
echo ""
echo "TensorRT note: first run will be slow (engine compilation). Subsequent"
echo "runs load from cache (~/.local/share/bgremove/trt_cache)."
echo ""
echo "If TensorRT isn't installed, pass --no-trt to use CUDA EP instead."
