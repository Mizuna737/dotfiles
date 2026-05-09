#!/usr/bin/env python3
"""
diskHealthRefresh.py
Collects SMART health data for all internal drives and writes
~/.cache/dashboard/diskHealth.json for the dashboard tile.

Requires passwordless sudo for /usr/bin/smartctl — see
/etc/sudoers.d/dashboardSmartctl.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

CACHE_DIR = os.path.expanduser("~/.cache/dashboard")
HEALTH_FILE = os.path.join(CACHE_DIR, "diskHealth.json")


def _runJson(cmd):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        return json.loads(result.stdout)
    except Exception:
        return {}


def _enumerateDrives():
    data = _runJson(["lsblk", "-d", "-nJo", "NAME,TRAN,MODEL,SIZE"])
    drives = []
    for dev in data.get("blockdevices", []):
        tran = (dev.get("tran") or "").lower()
        if tran in ("nvme", "sata"):
            drives.append({
                "name": dev.get("name", ""),
                "tran": tran,
                "model": dev.get("model", ""),
                "size": dev.get("size", ""),
            })
    return drives


def _parseNvme(smart):
    log = smart.get("nvme_smart_health_information_log", {})
    selfTestLog = smart.get("nvme_self_test_log", {})

    criticalWarning = log.get("critical_warning", 0)
    availableSpare = log.get("available_spare", 100)
    percentageUsed = log.get("percentage_used", 0)
    mediaErrors = log.get("media_errors", 0)
    numErrLogEntries = log.get("num_err_log_entries", 0)
    temp = log.get("temperature", None)
    powerOnHours = smart.get("power_on_time", {}).get("hours", None)

    lastShortTest = None
    lastLongTest = None
    for entry in selfTestLog.get("table", []):
        testType = entry.get("self_test_code", {}).get("string", "").lower()
        result = entry.get("self_test_result", {}).get("string", "unknown").lower()
        ts = entry.get("power_on_hours", None)
        testObj = {"powerOnHours": ts, "result": result}
        if "short" in testType and lastShortTest is None:
            lastShortTest = testObj
        elif "extended" in testType and lastLongTest is None:
            lastLongTest = testObj

    return {
        "criticalWarning": criticalWarning,
        "availableSpare": availableSpare,
        "percentageUsed": percentageUsed,
        "mediaErrors": mediaErrors,
        "numErrLogEntries": numErrLogEntries,
        "tempC": temp,
        "powerOnHours": powerOnHours,
        "lastShortTest": lastShortTest,
        "lastLongTest": lastLongTest,
    }


def _parseSata(smart):
    attrTable = smart.get("ata_smart_attributes", {}).get("table", [])
    attrById = {a["id"]: a for a in attrTable if "id" in a}
    attrByName = {a.get("name", ""): a for a in attrTable}

    def rawVal(attrId, attrName=None):
        entry = attrById.get(attrId) or (attrByName.get(attrName) if attrName else None)
        if entry:
            raw = entry.get("raw", {})
            return raw.get("value", 0) if isinstance(raw, dict) else 0
        return 0

    def normVal(attrId, attrName=None):
        entry = attrById.get(attrId) or (attrByName.get(attrName) if attrName else None)
        if entry:
            return entry.get("value", 100)
        return None

    reallocated = rawVal(5, "Reallocated_Sector_Ct")
    pendingSectors = rawVal(197, "Current_Pending_Sector")
    uncorrectable = rawVal(198, "Offline_Uncorrectable")
    wearLevelNorm = normVal(177, "Wear_Leveling_Count")
    ssdLifeLeft = normVal(231, "SSD_Life_Left")

    # Infer percentageUsed from wear attributes
    # Wear_Leveling_Count: 100 = new, lower = more worn
    # SSD_Life_Left: 100 = new, lower = more worn
    percentageUsed = None
    if ssdLifeLeft is not None:
        percentageUsed = 100 - ssdLifeLeft
    elif wearLevelNorm is not None:
        percentageUsed = 100 - wearLevelNorm

    tempC = smart.get("temperature", {}).get("current", None)
    powerOnHours = smart.get("power_on_time", {}).get("hours", None)

    # Self-test log
    lastShortTest = None
    lastLongTest = None
    testTable = (
        smart.get("ata_smart_self_test_log", {})
             .get("standard", {})
             .get("table", [])
    )
    now = datetime.now(timezone.utc)
    for entry in testTable:
        typeStr = entry.get("type", {}).get("string", "").lower()
        resultStr = entry.get("status", {}).get("string", "unknown").lower()
        # Convert to a plain "passed/failed/unknown"
        if "completed without error" in resultStr or "passed" in resultStr:
            result = "passed"
        elif "in progress" in resultStr:
            result = "inProgress"
        elif "aborted" in resultStr or "interrupted" in resultStr:
            result = "aborted"
        else:
            result = "failed" if resultStr != "unknown" else "unknown"
        # Timestamp from lifetime hours — convert to ISO if possible
        lifeHours = entry.get("lifetime_hours", None)
        testObj = {"lifetimeHours": lifeHours, "result": result}
        if "short" in typeStr and lastShortTest is None:
            lastShortTest = testObj
        elif ("extended" in typeStr or "long" in typeStr) and lastLongTest is None:
            lastLongTest = testObj

    return {
        "reallocatedSectors": reallocated,
        "pendingSectors": pendingSectors,
        "uncorrectable": uncorrectable,
        "percentageUsed": percentageUsed,
        "tempC": tempC,
        "powerOnHours": powerOnHours,
        "lastShortTest": lastShortTest,
        "lastLongTest": lastLongTest,
    }


def _daysSinceTestHours(currentHours, testHours):
    """Approximate days since a test ran based on lifetime hour delta."""
    if currentHours is None or testHours is None:
        return None
    deltHours = currentHours - testHours
    return deltHours / 24.0 if deltHours >= 0 else None


def _assessDisk(tran, parsed, powerOnHours):
    reasons = []
    status = "green"

    def setStatus(s):
        nonlocal status
        if s == "red" or (s == "yellow" and status == "green"):
            status = s

    if tran == "nvme":
        if parsed["criticalWarning"] != 0:
            setStatus("red")
            reasons.append(f"critical_warning={parsed['criticalWarning']}")
        if parsed["availableSpare"] < 25:
            setStatus("red")
            reasons.append(f"available_spare {parsed['availableSpare']}% < 25 — critical")
        elif parsed["availableSpare"] < 50:
            setStatus("yellow")
            reasons.append(f"available_spare {parsed['availableSpare']}% < 50 — yellow")
        if parsed["percentageUsed"] > 80:
            setStatus("yellow")
            reasons.append(f"percentage_used {parsed['percentageUsed']}% > 80 — yellow")
        if parsed["mediaErrors"] > 0:
            setStatus("yellow")
            reasons.append(f"media_errors={parsed['mediaErrors']} — yellow")
        tempC = parsed.get("tempC")
        if tempC is not None and tempC > 60:
            setStatus("yellow")
            reasons.append(f"temp {tempC}°C > 60 — yellow")
        # Self-test staleness — NVMe tests store power-on hours not timestamps
        # We can only check if tests exist at all for NVMe
        if parsed["lastShortTest"] is None:
            setStatus("yellow")
            reasons.append("no short self-test on record — yellow")
        elif isinstance(parsed["lastShortTest"], dict):
            r = parsed["lastShortTest"].get("result", "")
            if r == "failed":
                setStatus("red")
                reasons.append("last short self-test failed — red")
        if parsed["lastLongTest"] is None:
            setStatus("yellow")
            reasons.append("no long self-test on record — yellow")
        elif isinstance(parsed["lastLongTest"], dict):
            r = parsed["lastLongTest"].get("result", "")
            if r == "failed":
                setStatus("red")
                reasons.append("last long self-test failed — red")

    else:  # sata
        if parsed["reallocatedSectors"] > 0:
            setStatus("red")
            reasons.append(f"reallocated_sectors={parsed['reallocatedSectors']} — red")
        if parsed["pendingSectors"] > 0:
            setStatus("red")
            reasons.append(f"pending_sectors={parsed['pendingSectors']} — red")
        if parsed["uncorrectable"] > 0:
            setStatus("red")
            reasons.append(f"uncorrectable={parsed['uncorrectable']} — red")
        if parsed["percentageUsed"] is not None and parsed["percentageUsed"] > 80:
            setStatus("yellow")
            reasons.append(f"percentage_used {parsed['percentageUsed']}% > 80 — yellow")
        tempC = parsed.get("tempC")
        if tempC is not None and tempC > 60:
            setStatus("yellow")
            reasons.append(f"temp {tempC}°C > 60 — yellow")

        # Self-test staleness
        def checkTestStaleness(testObj, label, staleThreshDays):
            if testObj is None:
                setStatus("yellow")
                reasons.append(f"no {label} self-test on record — yellow")
                return
            result = testObj.get("result", "unknown")
            if result == "failed":
                setStatus("red")
                reasons.append(f"last {label} self-test failed — red")
                return
            lifeHours = testObj.get("lifetimeHours")
            daysSince = _daysSinceTestHours(powerOnHours, lifeHours)
            if daysSince is not None and daysSince > staleThreshDays:
                setStatus("yellow")
                reasons.append(
                    f"last {label} self-test {int(daysSince)} days ago (>{staleThreshDays}) — yellow"
                )

        checkTestStaleness(parsed["lastShortTest"], "short", 10)
        checkTestStaleness(parsed["lastLongTest"], "long", 40)

    return status, reasons


def refreshDiskHealth():
    os.makedirs(CACHE_DIR, exist_ok=True)

    drives = _enumerateDrives()
    diskResults = []
    worstStatus = "green"
    statusOrder = {"green": 0, "yellow": 1, "red": 2}

    for drive in drives:
        name = drive["name"]
        tran = drive["tran"]
        devPath = f"/dev/{name}"

        smart = _runJson(["sudo", "/usr/bin/smartctl", "-aj", devPath])

        if tran == "nvme":
            parsed = _parseNvme(smart)
            status, reasons = _assessDisk(tran, parsed, parsed.get("powerOnHours"))

            # Derive a sizeBytes from lsblk size string if possible
            entry = {
                "name": name,
                "model": drive["model"],
                "size": drive["size"],
                "tran": tran,
                "status": status,
                "percentUsed": parsed["percentageUsed"],
                "availableSpare": parsed["availableSpare"],
                "criticalWarning": parsed["criticalWarning"],
                "mediaErrors": parsed["mediaErrors"],
                "numErrLogEntries": parsed["numErrLogEntries"],
                "tempC": parsed["tempC"],
                "powerOnHours": parsed["powerOnHours"],
                "lastShortTest": parsed["lastShortTest"],
                "lastLongTest": parsed["lastLongTest"],
                "reasons": reasons,
            }
        else:
            parsed = _parseSata(smart)
            status, reasons = _assessDisk(tran, parsed, parsed.get("powerOnHours"))

            entry = {
                "name": name,
                "model": drive["model"],
                "size": drive["size"],
                "tran": tran,
                "status": status,
                "percentUsed": parsed["percentageUsed"],
                "availableSpare": None,
                "reallocatedSectors": parsed["reallocatedSectors"],
                "pendingSectors": parsed["pendingSectors"],
                "uncorrectable": parsed["uncorrectable"],
                "tempC": parsed["tempC"],
                "powerOnHours": parsed["powerOnHours"],
                "lastShortTest": parsed["lastShortTest"],
                "lastLongTest": parsed["lastLongTest"],
                "reasons": reasons,
            }

        diskResults.append(entry)
        if statusOrder.get(status, 0) > statusOrder.get(worstStatus, 0):
            worstStatus = status

    snapshot = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "worstStatus": worstStatus,
        "disks": diskResults,
    }

    tmpPath = HEALTH_FILE + ".tmp"
    with open(tmpPath, "w") as f:
        json.dump(snapshot, f, indent=2)
    os.replace(tmpPath, HEALTH_FILE)

    return snapshot


def _daemonLoop():
    while True:
        try:
            refreshDiskHealth()
        except Exception as e:
            print(f"diskHealthRefresh daemon error: {e}", file=sys.stderr)
        time.sleep(900)


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        _daemonLoop()
    else:
        snapshot = refreshDiskHealth()
        print(json.dumps(snapshot, indent=2))
