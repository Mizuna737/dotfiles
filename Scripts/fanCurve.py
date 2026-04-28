#!/usr/bin/env python3
"""CPU-temp-driven fan curve daemon for MSI nct6687 board.

Drives pwm3 (SYS_FAN1) via a piecewise-linear curve read from
~/.config/fanCurve/curve.toml. All other pwm channels are pinned at full.
Restores original pwm state on exit.
"""

import os
import sys
import signal
import atexit
import time
import tomllib
from pathlib import Path

CONFIG_PATH = Path("/home/max/.config/fanCurve/curve.toml")
DEFAULT_CONFIG = """\
# Fan curve for SYS_FAN1 (pwm3 on nct6687).
# Linear interpolation between points. Edit and save — fanCurve daemon picks up changes live.
# Tctl °C → pwm (0–255).

[[points]]
temp = 65
pwm  = 63

[[points]]
temp = 70
pwm  = 80

[[points]]
temp = 75
pwm  = 120

[[points]]
temp = 80
pwm  = 200

[[points]]
temp = 85
pwm  = 255
"""

POLL_INTERVAL = 2.0        # seconds
EMA_ALPHA = 0.2            # ≈10s effective window at 2s poll
HYSTERESIS = 2.0           # °C — minimum delta to act on
TRIP_THRESHOLD = 90.0      # °C raw — safety floor, go full blast
CURVE_CHANNEL = 3          # pwm3
FULL_CHANNELS = [1, 2, 4, 5, 6, 7, 8]
NUM_CHANNELS = 8


# ---------- hardware discovery ----------

def findHwmonByName(targetName: str) -> Path:
    """Return the hwmon path whose 'name' file matches targetName."""
    for hwmon in Path("/sys/class/hwmon").iterdir():
        namePath = hwmon / "name"
        if namePath.exists() and namePath.read_text().strip() == targetName:
            return hwmon
    raise RuntimeError(f"hwmon device '{targetName}' not found")


def readSysInt(path: Path) -> int:
    return int(path.read_text().strip())


def writeSysInt(path: Path, value: int) -> None:
    path.write_text(str(value))


# ---------- pwm helpers ----------

def pwmPath(hwmon: Path, channel: int) -> Path:
    return hwmon / f"pwm{channel}"


def pwmEnablePath(hwmon: Path, channel: int) -> Path:
    return hwmon / f"pwm{channel}_enable"


def saveOriginals(hwmon: Path) -> dict:
    originals = {}
    for ch in range(1, NUM_CHANNELS + 1):
        try:
            originals[ch] = {
                "enable": readSysInt(pwmEnablePath(hwmon, ch)),
                "pwm": readSysInt(pwmPath(hwmon, ch)),
            }
        except Exception:
            originals[ch] = {"enable": None, "pwm": None}
    return originals


def restoreOriginals(hwmon: Path, originals: dict) -> None:
    for ch in range(1, NUM_CHANNELS + 1):
        orig = originals.get(ch, {})
        try:
            if orig.get("enable") is not None:
                writeSysInt(pwmEnablePath(hwmon, ch), orig["enable"])
            if orig.get("pwm") is not None:
                writeSysInt(pwmPath(hwmon, ch), orig["pwm"])
        except Exception as exc:
            print(f"[fanCurve] WARNING: could not restore pwm{ch}: {exc}", flush=True)


# ---------- config ----------

def loadConfig(path: Path) -> list[dict]:
    """Parse curve.toml and return sorted list of {temp, pwm} dicts."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    points = data.get("points", [])
    if not points:
        raise ValueError("curve.toml has no [[points]] entries")
    for p in points:
        if "temp" not in p or "pwm" not in p:
            raise ValueError(f"curve point missing temp or pwm: {p}")
    return sorted(points, key=lambda p: p["temp"])


def ensureConfig(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_CONFIG)
        print(f"[fanCurve] wrote default config to {path}", flush=True)


# ---------- curve math ----------

def interpolatePwm(curvePoints: list[dict], temp: float) -> int:
    """Piecewise linear interpolation; clamp outside the curve endpoints."""
    if temp <= curvePoints[0]["temp"]:
        return int(curvePoints[0]["pwm"])
    if temp >= curvePoints[-1]["temp"]:
        return int(curvePoints[-1]["pwm"])
    for i in range(len(curvePoints) - 1):
        lo, hi = curvePoints[i], curvePoints[i + 1]
        if lo["temp"] <= temp <= hi["temp"]:
            frac = (temp - lo["temp"]) / (hi["temp"] - lo["temp"])
            return int(round(lo["pwm"] + frac * (hi["pwm"] - lo["pwm"])))
    return int(curvePoints[-1]["pwm"])


# ---------- main ----------

def main() -> None:
    if os.geteuid() != 0:
        print("[fanCurve] ERROR: must run as root (euid 0)", flush=True)
        sys.exit(1)

    # discover hardware
    try:
        nctHwmon = findHwmonByName("nct6687")
    except RuntimeError as exc:
        print(f"[fanCurve] ERROR: {exc}", flush=True)
        sys.exit(1)

    try:
        k10Hwmon = findHwmonByName("k10temp")
    except RuntimeError as exc:
        print(f"[fanCurve] ERROR: {exc}", flush=True)
        sys.exit(1)

    print(f"[fanCurve] nct6687 at {nctHwmon}", flush=True)
    print(f"[fanCurve] k10temp  at {k10Hwmon}", flush=True)

    # config
    ensureConfig(CONFIG_PATH)
    try:
        curvePoints = loadConfig(CONFIG_PATH)
    except Exception as exc:
        print(f"[fanCurve] ERROR loading config: {exc}", flush=True)
        sys.exit(1)
    configMtime = CONFIG_PATH.stat().st_mtime

    # save originals before touching anything
    originals = saveOriginals(nctHwmon)

    # restore on any exit path
    def cleanup() -> None:
        print("[fanCurve] restoring original pwm state", flush=True)
        restoreOriginals(nctHwmon, originals)

    atexit.register(cleanup)

    def sigHandler(signum, frame) -> None:
        sys.exit(0)  # triggers atexit

    signal.signal(signal.SIGTERM, sigHandler)
    signal.signal(signal.SIGINT, sigHandler)

    # pin non-curve channels to full speed
    for ch in FULL_CHANNELS:
        try:
            writeSysInt(pwmEnablePath(nctHwmon, ch), 1)
            writeSysInt(pwmPath(nctHwmon, ch), 255)
        except Exception as exc:
            print(f"[fanCurve] WARNING: could not pin pwm{ch}: {exc}", flush=True)

    # take control of pwm3
    writeSysInt(pwmEnablePath(nctHwmon, CURVE_CHANNEL), 1)
    print(f"[fanCurve] daemon owns pwm{CURVE_CHANNEL}, starting loop", flush=True)

    # initial state
    smoothedTemp: float | None = None
    lastAppliedTemp: float | None = None
    lastAppliedPwm: int | None = None
    inTrip = False

    tempPath = k10Hwmon / "temp1_input"

    try:
        while True:
            # --- config reload ---
            try:
                curMtime = CONFIG_PATH.stat().st_mtime
                if curMtime != configMtime:
                    newPoints = loadConfig(CONFIG_PATH)
                    curvePoints = newPoints
                    configMtime = curMtime
                    print(f"[fanCurve] config reloaded ({len(curvePoints)} points)", flush=True)
            except Exception as exc:
                print(f"[fanCurve] WARNING: config reload failed: {exc}", flush=True)

            # --- read temp ---
            try:
                rawMillideg = readSysInt(tempPath)
                rawTemp = rawMillideg / 1000.0
                readOk = True
            except Exception as exc:
                print(f"[fanCurve] WARNING: temp read failed: {exc}", flush=True)
                readOk = False

            if not readOk or rawTemp > TRIP_THRESHOLD:
                if not inTrip:
                    inTrip = True
                    reason = f"rawTemp={rawTemp:.1f}°C" if readOk else "sensor read failure"
                    print(f"[fanCurve] TRIP: {reason} — forcing pwm{CURVE_CHANNEL}=255", flush=True)
                writeSysInt(pwmPath(nctHwmon, CURVE_CHANNEL), 255)
                time.sleep(POLL_INTERVAL)
                continue

            if inTrip:
                inTrip = False
                print(f"[fanCurve] TRIP cleared, rawTemp={rawTemp:.1f}°C", flush=True)

            # --- EMA smoothing ---
            if smoothedTemp is None:
                smoothedTemp = rawTemp
            else:
                smoothedTemp = EMA_ALPHA * rawTemp + (1 - EMA_ALPHA) * smoothedTemp

            # --- hysteresis gate ---
            if lastAppliedTemp is not None and abs(smoothedTemp - lastAppliedTemp) < HYSTERESIS:
                time.sleep(POLL_INTERVAL)
                continue

            # --- interpolate and write ---
            targetPwm = max(0, min(255, interpolatePwm(curvePoints, smoothedTemp)))

            if targetPwm != lastAppliedPwm:
                writeSysInt(pwmPath(nctHwmon, CURVE_CHANNEL), targetPwm)
                print(
                    f"[fanCurve] Tctl={smoothedTemp:.1f}°C (raw={rawTemp:.1f}) "
                    f"→ pwm{CURVE_CHANNEL}={targetPwm}",
                    flush=True,
                )
                lastAppliedPwm = targetPwm

            lastAppliedTemp = smoothedTemp
            time.sleep(POLL_INTERVAL)

    finally:
        pass  # atexit handles cleanup


if __name__ == "__main__":
    main()
