#!/usr/bin/env python3
"""fanMap.py — Identify which pwm channel controls SYS_FAN1 (fan1_input).

Sweeps pwm channels 1..8 on the nct6687 hwmon path, driving each to low (64)
and high (255) and measuring fan1_input RPM. The channel with the largest
delta is SYS_FAN1.

Must be run as root.
"""

import os
import signal
import sys
import time

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def findHwmon(chipName: str) -> str:
    """Return the sysfs hwmon path for the named chip, or raise."""
    base = "/sys/class/hwmon"
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry)
        namePath = os.path.join(path, "name")
        try:
            with open(namePath) as f:
                if f.read().strip() == chipName:
                    return path
        except OSError:
            continue
    raise RuntimeError(f"hwmon chip '{chipName}' not found under {base}")


def readInt(path: str) -> int:
    with open(path) as f:
        return int(f.read().strip())


def writeInt(path: str, value: int) -> None:
    with open(path, "w") as f:
        f.write(str(value) + "\n")


def sampleFan(hwmon: str, fanFile: str, count: int = 3, interval: float = 1.0) -> int:
    """Sample fan RPM `count` times at `interval` seconds apart, return median."""
    samples = []
    for _ in range(count):
        samples.append(readInt(os.path.join(hwmon, fanFile)))
        time.sleep(interval)
    samples.sort()
    return samples[len(samples) // 2]


# --------------------------------------------------------------------------- #
# Restore state tracking
# --------------------------------------------------------------------------- #

# Dict: channel -> (origEnable, origPwm)
_savedState: dict[int, tuple[int, int]] = {}
_hwmon: str = ""


def restoreAll() -> None:
    """Restore all saved pwm channels to original enable+pwm values."""
    for ch, (origEnable, origPwm) in _savedState.items():
        enablePath = os.path.join(_hwmon, f"pwm{ch}_enable")
        pwmPath = os.path.join(_hwmon, f"pwm{ch}")
        try:
            writeInt(enablePath, origEnable)
            writeInt(pwmPath, origPwm)
        except OSError as e:
            print(f"  [warn] could not restore pwm{ch}: {e}", file=sys.stderr)


def signalHandler(sig, frame):
    print(f"\nCaught signal {sig}, restoring fan settings...", file=sys.stderr)
    restoreAll()
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    global _hwmon

    if os.geteuid() != 0:
        print("Error: fanMap.py must be run as root (sudo python3 fanMap.py).", file=sys.stderr)
        sys.exit(1)

    _hwmon = findHwmon("nct6687")
    print(f"Found nct6687 at: {_hwmon}")
    print(f"Baseline fan1_input: {readInt(os.path.join(_hwmon, 'fan1_input'))} RPM")
    print()

    signal.signal(signal.SIGINT, signalHandler)
    signal.signal(signal.SIGTERM, signalHandler)

    results: list[tuple[int, int, int, int]] = []  # (channel, lowRpm, highRpm, delta)

    for ch in range(1, 9):
        enablePath = os.path.join(_hwmon, f"pwm{ch}_enable")
        pwmPath = os.path.join(_hwmon, f"pwm{ch}")

        # Save originals
        origEnable = readInt(enablePath)
        origPwm = readInt(pwmPath)
        _savedState[ch] = (origEnable, origPwm)

        print(f"Channel pwm{ch}: saved enable={origEnable} pwm={origPwm}")

        try:
            # Set manual mode
            writeInt(enablePath, 1)

            # Low speed
            writeInt(pwmPath, 64)
            print(f"  -> pwm=64, settling 4s...", end="", flush=True)
            time.sleep(4)
            lowRpm = sampleFan(_hwmon, "fan1_input", count=3, interval=1.0)
            print(f" lowRpm={lowRpm}")

            # High speed
            writeInt(pwmPath, 255)
            print(f"  -> pwm=255, settling 4s...", end="", flush=True)
            time.sleep(4)
            highRpm = sampleFan(_hwmon, "fan1_input", count=3, interval=1.0)
            print(f" highRpm={highRpm}")

        finally:
            # Always restore this channel before moving to the next
            writeInt(enablePath, origEnable)
            writeInt(pwmPath, origPwm)
            del _savedState[ch]
            print(f"  -> restored pwm{ch}")

        delta = highRpm - lowRpm
        results.append((ch, lowRpm, highRpm, delta))

    # Print summary table
    print()
    print(f"{'Channel':<10} {'lowRpm':>8} {'highRpm':>9} {'delta':>7}")
    print("-" * 38)
    for ch, lowRpm, highRpm, delta in results:
        print(f"pwm{ch:<7} {lowRpm:>8} {highRpm:>9} {delta:>7}")

    bestCh, bestLow, bestHigh, bestDelta = max(results, key=lambda r: r[3])
    print()
    print(f"SYS_FAN1 is on pwm{bestCh}  (delta={bestDelta} RPM, {bestLow}→{bestHigh})")


if __name__ == "__main__":
    main()
