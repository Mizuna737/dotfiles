"""droidcamScan.py — fast DroidCam device discovery.

Resolution order per device:
  1. ARP table lookup by MAC (zero network traffic)
  2. Direct TCP connect to last-known IP
  3. Parallel threaded /24 scan (254 simultaneous connections)

Successful resolves update ip/mac in the yaml config atomically.
"""

import os
import queue
import socket
import subprocess
import threading
from pathlib import Path


# ---------------------------------------------------------------------------
# ARP helpers
# ---------------------------------------------------------------------------

def arpLookupByMac(mac: str) -> str | None:
    """Return IP for mac from ARP table (REACHABLE/STALE/DELAY/PERMANENT), or None."""
    try:
        out = subprocess.check_output(["ip", "neigh", "show"], text=True, timeout=2)
    except Exception:
        return None
    mac_lower = mac.lower()
    for line in out.splitlines():
        if mac_lower not in line.lower():
            continue
        parts = line.split()
        if not parts or not parts[0][0].isdigit():
            continue
        state = parts[-1]
        if state in ("REACHABLE", "STALE", "DELAY", "PERMANENT"):
            return parts[0]
    return None


def getMacFromArp(ip: str) -> str | None:
    """Return MAC address for ip from ARP table, or None."""
    try:
        out = subprocess.check_output(["ip", "neigh", "show", ip], text=True, timeout=2)
    except Exception:
        return None
    for line in out.splitlines():
        parts = line.split()
        if "lladdr" in parts:
            idx = parts.index("lladdr")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return None


# ---------------------------------------------------------------------------
# Parallel scan
# ---------------------------------------------------------------------------

def parallelScan(referenceIp: str, port: int, timeout: float = 0.5) -> str | None:
    """Scan all hosts on the /24 of referenceIp in parallel. Returns first hit or None."""
    prefix = ".".join(referenceIp.split(".")[:3])
    result_q: queue.Queue[str] = queue.Queue()
    stop_event = threading.Event()

    def tryHost(host: str) -> None:
        if stop_event.is_set():
            return
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            result_q.put(host)
            stop_event.set()
        except (OSError, socket.timeout):
            pass

    threads = [
        threading.Thread(target=tryHost, args=(f"{prefix}.{i}",), daemon=True)
        for i in range(1, 255)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout + 1.0)

    try:
        return result_q.get_nowait()
    except queue.Empty:
        return None


# ---------------------------------------------------------------------------
# Device resolution
# ---------------------------------------------------------------------------

def findDevice(device: dict) -> tuple[str, int] | None:
    """Resolve a single device dict to (ip, port). Updates device dict in-place on success."""
    port = int(device.get("port", 4747))
    mac = device.get("mac") or None
    lastIp = device.get("ip") or ""

    def _tryConnect(ip: str) -> bool:
        try:
            sock = socket.create_connection((ip, port), timeout=0.5)
            sock.close()
            return True
        except (OSError, socket.timeout):
            return False

    def _onSuccess(ip: str) -> tuple[str, int]:
        device["ip"] = ip
        if not device.get("mac"):
            device["mac"] = getMacFromArp(ip)
        return ip, port

    # 1. ARP by MAC — zero traffic
    if mac:
        arpIp = arpLookupByMac(mac)
        if arpIp and _tryConnect(arpIp):
            return _onSuccess(arpIp)

    # 2. Last-known IP direct connect
    if lastIp and _tryConnect(lastIp):
        return _onSuccess(lastIp)

    # 3. Parallel subnet scan
    refIp = lastIp or "192.168.0.1"
    found = parallelScan(refIp, port)
    if found:
        return _onSuccess(found)

    return None


# ---------------------------------------------------------------------------
# Multi-device config interface
# ---------------------------------------------------------------------------

def findFirstReachable(configPath: str) -> tuple[str, int, str] | None:
    """Load yaml config, resolve each device, return (ip, port, name) for first reachable.

    Saves updated ip/mac back to config atomically on success.
    """
    import yaml

    cfgPath = Path(configPath)
    try:
        cfg = yaml.safe_load(cfgPath.read_text())
    except Exception:
        return None

    devices = cfg.get("devices", [])
    found = None

    for device in devices:
        r = findDevice(device)
        if r:
            found = (r[0], r[1], str(device.get("name", "unknown")))
            break

    if found:
        tmpPath = str(cfgPath) + ".tmp"
        try:
            with open(tmpPath, "w") as f:
                yaml.dump(cfg, f, default_flow_style=False)
            os.replace(tmpPath, str(cfgPath))
        except Exception:
            pass

    return found


# ---------------------------------------------------------------------------
# Backward-compat shim for existing callers
# ---------------------------------------------------------------------------

def find_droidcam(ip: str, port: int = 4747, timeout: float = 0.5) -> tuple[str, int]:
    """Legacy API: resolve single ip/port. Returns (host, port) — never raises."""
    device = {"mac": None, "ip": ip, "port": port}
    result = findDevice(device)
    return result if result else (ip, port)
