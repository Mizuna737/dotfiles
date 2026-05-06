"""droidcamScan.py — subnet scan for DroidCam phone on port 4747.

Usage:
    host, port = find_droidcam("192.168.0.106", port=4747)
    # Returns the first reachable IP on the subnet, or falls back to `ip` if nothing responds.
"""

import socket
import threading
import time

_cache = {"host": None, "port": None, "time": 0.0}
_CACHE_TTL = 60  # seconds


def _scan_subnet(ip, port, timeout=0.5, max_hosts=254):
    """Scan 1..max_hosts on the same /24, return (host, port) or None."""
    prefix = ".".join(ip.split(".")[:3])
    for i in range(1, max_hosts + 1):
        host = f"{prefix}.{i}"
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            return host, port
        except (OSError, socket.timeout):
            continue
    return None


def find_droidcam(ip, port=4747, timeout=0.5):
    """Find a reachable DroidCam phone by trying `ip` first, then scanning subnet.

    Results are cached for _CACHE_TTL seconds.  If nothing responds, falls back
    to the provided `ip` (last known good).
    """
    now = time.monotonic()
    if _cache["host"] and (now - _cache["time"]) < _CACHE_TTL:
        return _cache["host"], _cache["port"]

    # Try the known IP first (fast path)
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
        sock.close()
        _cache["host"] = ip
        _cache["port"] = port
        _cache["time"] = time.monotonic()
        return ip, port
    except (OSError, socket.timeout):
        pass

    # Fall back to subnet scan
    result = _scan_subnet(ip, port, timeout=timeout)
    if result:
        _cache["host"] = result[0]
        _cache["port"] = result[1]
        _cache["time"] = time.monotonic()
        return result
    else:
        # Nothing responded — return last known IP anyway (fallback)
        _cache["host"] = ip
        _cache["port"] = port
        _cache["time"] = time.monotonic()
        return ip, port
