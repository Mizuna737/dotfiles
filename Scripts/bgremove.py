#!/usr/bin/env python3
"""
bgremove.py — GPU-accelerated background removal virtual camera.
Uses Robust Video Matting (RVM) via ONNX Runtime with TensorRT FP16 EP.
Reads from a v4l2 device, composites over a chosen background, and
writes to a v4l2loopback virtual camera.

Usage:
  python bgremove.py [--input /dev/video20] [--output /dev/video21]
                     [--background blur|green|black|white|#RRGGBB|/path/img]
                     [--downsample 0.5] [--no-trt]

Background switching without restart:
  echo "/path/to/image.jpg" > ~/.cache/bgremove.bg   # or "blur", "green", etc.
  kill -USR1 <pid>
"""

import argparse
import os
import signal
import socket
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import pyfakewebcam

DEBUG = False


def loadDroidcamEndpoint():
    cfg = os.path.expanduser("~/.config/droidcam")
    host, port = "192.168.0.156", 4747
    try:
        with open(cfg) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ip="):
                    host = line.split("=", 1)[1].strip() or host
                elif line.startswith("port="):
                    try:
                        port = int(line.split("=", 1)[1].strip())
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return host, port


def isDroidcamReachable(host, port, timeout=1.0):
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def parseArgs():
    _dcHost, _dcPort = loadDroidcamEndpoint()
    p = argparse.ArgumentParser(description="GPU background removal virtual camera")
    p.add_argument("--input",      default="/dev/video20",
                   help="Source v4l2 device (droidcam output)")
    p.add_argument("--output",     default="/dev/video21",
                   help="Destination v4l2loopback device")
    p.add_argument("--width",      type=int, default=1280)
    p.add_argument("--height",     type=int, default=720)
    p.add_argument("--fps",        type=int, default=30)
    p.add_argument("--model",      default="~/.local/share/bgremove/rvm_mobilenetv3.onnx",
                   help="Path to RVM ONNX model")
    p.add_argument("--background", default="blur",
                   help="blur | green | black | white | #RRGGBB | /path/to/image.jpg")
    p.add_argument("--blur-strength", type=int, default=51,
                   help="Gaussian blur kernel size (must be odd)")
    p.add_argument("--downsample", type=float, default=0.5,
                   help="RVM inference downsample ratio (0.25–1.0); lower = faster")
    p.add_argument("--no-trt",     action="store_true",
                   help="Skip TensorRT EP, use CUDA EP only")
    p.add_argument("--trt-cache",  default="~/.local/share/bgremove/trt_cache",
                   help="TensorRT engine cache directory (persists between runs)")
    p.add_argument("--droidcam-host", default=_dcHost,
                   help="Droidcam phone IP (default from ~/.config/droidcam)")
    p.add_argument("--droidcam-port", type=int, default=_dcPort,
                   help="Droidcam phone port (default from ~/.config/droidcam)")
    p.add_argument("--no-droidcam-gate", action="store_true",
                   help="Disable TCP reachability gate (use for non-droidcam inputs)")
    p.add_argument("--debug",      action="store_true")
    return p.parse_args()


# ── ONNX / TensorRT providers ────────────────────────────────────────────────

def buildProviders(noTrt, trtCacheDir):
    trtCachePath = Path(trtCacheDir).expanduser()
    trtCachePath.mkdir(parents=True, exist_ok=True)

    if not noTrt:
        return [
            ("TensorrtExecutionProvider", {
                "device_id": 0,
                "trt_fp16_enable": True,
                "trt_engine_cache_enable": True,
                "trt_engine_cache_path": str(trtCachePath),
                "trt_max_workspace_size": 2 << 30,  # 2 GiB
            }),
            ("CUDAExecutionProvider", {"device_id": 0}),
            "CPUExecutionProvider",
        ]
    return [
        ("CUDAExecutionProvider", {"device_id": 0}),
        "CPUExecutionProvider",
    ]


# ── Background parsing ────────────────────────────────────────────────────────

_NAMED_COLORS = {
    "green":  (0,   177, 64),   # broadcast chroma green
    "chroma": (0,   177, 64),
    "black":  (0,   0,   0),
    "white":  (255, 255, 255),
    "blue":   (0,   0,   255),
    "red":    (255, 0,   0),
}


def parseBackground(spec, width, height):
    """
    Returns one of:
      "blur"          — Gaussian blur of original frame
      np.ndarray      — (H, W, 3) uint8 RGB solid color or loaded image
    """
    spec = spec.strip()

    if spec in ("blur", "off"):
        return spec

    # File path
    if spec.startswith("/") or spec.startswith("~") or Path(spec).suffix in (".jpg", ".jpeg", ".png", ".webp"):
        imgPath = Path(spec).expanduser()
        img = cv2.imread(str(imgPath))
        if img is None:
            raise ValueError(f"Cannot load background image: {imgPath}")
        # Center-crop to 16:9 before resizing (handles ultrawide sources)
        srcH, srcW = img.shape[:2]
        targetAspect = 16.0 / 9.0
        srcAspect = srcW / srcH
        if srcAspect > targetAspect:
            cropW = int(srcH * targetAspect)
            x0 = (srcW - cropW) // 2
            img = img[:, x0:x0 + cropW]
        elif srcAspect < targetAspect:
            cropH = int(srcW / targetAspect)
            y0 = (srcH - cropH) // 2
            img = img[y0:y0 + cropH, :]
        img = cv2.resize(img, (width, height))
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Named color
    if spec in _NAMED_COLORS:
        r, g, b = _NAMED_COLORS[spec]
        return np.full((height, width, 3), [r, g, b], dtype=np.uint8)

    # Hex color
    if spec.startswith("#") and len(spec) == 7:
        r = int(spec[1:3], 16)
        g = int(spec[3:5], 16)
        b = int(spec[5:7], 16)
        return np.full((height, width, 3), [r, g, b], dtype=np.uint8)

    raise ValueError(f"Unknown background spec: '{spec}'. "
                     "Use: blur, green, black, white, #RRGGBB, or /path/to/image")


# ── Alpha compositing ─────────────────────────────────────────────────────────

def composite(frameRgb, alpha, background, blurStrength):
    """
    frameRgb:   (H, W, 3) uint8
    alpha:      (H, W, 1) float32  [0, 1]
    background: "blur" | (H, W, 3) uint8
    returns:    (H, W, 3) uint8
    """
    if isinstance(background, str):
        k = blurStrength | 1  # ensure odd
        bg = cv2.GaussianBlur(frameRgb, (k, k), 0)
    else:
        bg = background

    # Blend: out = frame * alpha + bg * (1 - alpha)
    a = alpha.astype(np.float32)
    out = frameRgb.astype(np.float32) * a + bg.astype(np.float32) * (1.0 - a)
    return out.astype(np.uint8)


# ── RVM segmenter ─────────────────────────────────────────────────────────────

class RVMSegmenter:
    """
    Robust Video Matting inference.
    Maintains recurrent hidden states across frames for temporal consistency.
    """

    _ZERO_STATE = np.zeros([1, 1, 1, 1], dtype=np.float32)

    def __init__(self, modelPath, providers, downsampleRatio):
        print(f"[bgremove] Loading model: {modelPath}")
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(modelPath), sess_options=opts,
                                            providers=providers)
        print(f"[bgremove] Active providers: {self.session.get_providers()}")
        self.downsampleRatio = np.array([downsampleRatio], dtype=np.float32)
        self.recState = [None, None, None, None]  # r1–r4

    def infer(self, frameRgb):
        """
        frameRgb: (H, W, 3) uint8
        returns alpha: (H, W, 1) float32 [0, 1]
        """
        src = frameRgb.astype(np.float32) / 255.0
        src = src.transpose(2, 0, 1)[np.newaxis]  # (1, 3, H, W)

        r1, r2, r3, r4 = [s if s is not None else self._ZERO_STATE
                           for s in self.recState]

        outputs = self.session.run(None, {
            "src":              src,
            "r1i":              r1,
            "r2i":              r2,
            "r3i":              r3,
            "r4i":              r4,
            "downsample_ratio": self.downsampleRatio,
        })
        _fgr, pha, r1o, r2o, r3o, r4o = outputs
        self.recState = [r1o, r2o, r3o, r4o]

        # pha: (1, 1, H, W) → (H, W, 1)
        return pha[0, 0, :, :, np.newaxis]

    def resetState(self):
        """Call after stream interruptions to avoid ghost artefacts."""
        self.recState = [None, None, None, None]


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    global DEBUG
    args = parseArgs()
    DEBUG = args.debug

    modelPath = Path(args.model).expanduser()
    if not modelPath.exists():
        print(f"[bgremove] Model not found: {modelPath}")
        print("[bgremove] Run:  Scripts/bgremove-setup.sh  to download it.")
        sys.exit(1)

    width, height = args.width, args.height
    frameInterval = 1.0 / args.fps

    print(f"[bgremove] Input:       {args.input}")
    print(f"[bgremove] Output:      {args.output}")
    print(f"[bgremove] Resolution:  {width}×{height} @ {args.fps} fps")
    print(f"[bgremove] Background:  {args.background}")
    print(f"[bgremove] Downsample:  {args.downsample}")
    print(f"[bgremove] TensorRT:    {'disabled' if args.no_trt else 'enabled (FP16)'}")

    # Open virtual camera output immediately so apps (Teams, etc.) can enumerate it
    camera      = pyfakewebcam.FakeWebcam(args.output, width, height)
    placeholder = np.zeros((height, width, 3), dtype=np.uint8)

    # Hot-reload background via SIGUSR1 + ~/.cache/bgremove.bg
    bgSwapFile = Path.home() / ".cache" / "bgremove.bg"

    # Restore previously selected background across reboots
    if bgSwapFile.exists():
        cached = bgSwapFile.read_text().strip()
        if cached:
            args.background = cached

    # Parse background
    background = parseBackground(args.background, width, height)

    def reloadBackground(sig, frame):
        nonlocal background
        if bgSwapFile.exists():
            spec = bgSwapFile.read_text().strip()
            try:
                background = parseBackground(spec, width, height)
                print(f"\n[bgremove] Background reloaded: {spec}")
            except Exception as e:
                print(f"\n[bgremove] Background reload failed: {e}")

    signal.signal(signal.SIGUSR1, reloadBackground)

    # Build ONNX/TRT session
    providers = buildProviders(args.no_trt, args.trt_cache)
    segmenter = RVMSegmenter(modelPath, providers, args.downsample)

    # Graceful shutdown
    running = True
    def shutdown(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("[bgremove] Running — Ctrl-C or SIGTERM to stop.")
    print(f"[bgremove] Hot-reload: echo 'blur' > {bgSwapFile} && kill -USR1 $$")

    frameCount  = 0
    fpsStart    = time.monotonic()
    inferTotal  = 0.0
    cap         = None

    probeIntervalSec = 2.0
    lastProbeTime    = 0.0
    lastProbeOk      = False

    while running:
        if not args.no_droidcam_gate:
            now = time.monotonic()
            if now - lastProbeTime >= probeIntervalSec:
                ok = isDroidcamReachable(args.droidcam_host, args.droidcam_port)
                if ok != lastProbeOk:
                    print(f"[bgremove] droidcam {'reachable' if ok else 'unreachable'} at {args.droidcam_host}:{args.droidcam_port}", flush=True)
                lastProbeOk = ok
                lastProbeTime = now
            if not lastProbeOk:
                camera.schedule_frame(placeholder)
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(1.0)
                continue

        # (Re)open input device if not available
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            cap = cv2.VideoCapture(args.input, cv2.CAP_V4L2)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv2.CAP_PROP_FPS,          args.fps)
                print(f"\n[bgremove] Input connected: {args.input}")
                segmenter.resetState()
                fpsStart = time.monotonic()
                inferTotal = 0.0
            else:
                cap.release()
                cap = None
                camera.schedule_frame(placeholder)
                time.sleep(1.0)
                continue

        ret, frame = cap.read()
        if not ret:
            print("\n[bgremove] Input lost — waiting for reconnect…")
            cap.release()
            cap = None
            segmenter.resetState()
            camera.schedule_frame(placeholder)
            time.sleep(0.5)
            continue

        frameRgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # Resize if capture returned different dimensions than requested
        if frameRgb.shape[1] != width or frameRgb.shape[0] != height:
            frameRgb = cv2.resize(frameRgb, (width, height))

        if isinstance(background, str) and background == "off":
            camera.schedule_frame(frameRgb)
            continue

        t0    = time.monotonic()
        alpha = segmenter.infer(frameRgb)
        inferTotal += time.monotonic() - t0

        out = composite(frameRgb, alpha, background, args.blur_strength)
        camera.schedule_frame(out)

        frameCount += 1
        if frameCount % 60 == 0:
            elapsed    = time.monotonic() - fpsStart
            fps        = 60 / elapsed
            avgInferMs = inferTotal / 60 * 1000
            print(f"[bgremove] {fps:.1f} fps  |  infer {avgInferMs:.1f} ms/frame", end="\r")
            fpsStart   = time.monotonic()
            inferTotal = 0.0

    if cap is not None:
        cap.release()
    print("\n[bgremove] Stopped.")


if __name__ == "__main__":
    main()
